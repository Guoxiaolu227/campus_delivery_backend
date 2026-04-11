"""
动态调度器（★ 阶段4核心）

职责：
  1. 维护每个骑手的"当前位置"和"剩余路线"
  2. 新订单到达时，用插入法快速分配到最佳骑手的最佳位置
  3. 支持"部分冻结"——正在走的路段不改，只调整后续路段
  4. 定期用短程 GA 对所有未完成路线做全局微调

架构：
  实时层：insert_order()       → 毫秒级，插入法
  定期层：periodic_reoptimize() → 秒级，短程 GA

"部分冻结"策略：
  骑手路线: 食堂 → A → B → C → D → 食堂
                      ↑正在走   ↑↑↑可调整
  frozen_index = 1（A 已锁定），可调整的是 [B, C, D]
"""

import threading
import time
import copy
import numpy as np
from flask import current_app


class CourierState:
    """
    单个骑手的运行时状态

    属性：
      courier_id:     骑手编号（1-based）
      full_route:     完整路线，如 [食堂, A, B, C, D, 食堂]
                      其中每个元素是 node_index（1-based）
      order_db_ids:   full_route 中每个位置对应的订单数据库 ID
                      full_route[0] 和 full_route[-1] 是食堂，对应 None
      frozen_index:   冻结指针——该骑手已完成/正在执行的最后一个位置下标
                      frozen_index=0 表示刚从食堂出发
                      frozen_index=1 表示正在前往 A 或已到达 A
      distance:       当前路线总距离
    """

    def __init__(self, courier_id, full_route, order_db_ids, distance=0):
        self.courier_id = courier_id
        self.full_route = full_route          # [canteen, o1, o2, ..., canteen]
        self.order_db_ids = order_db_ids      # [None, id1, id2, ..., None]
        self.frozen_index = 0                 # 0 = 刚出发
        self.distance = distance

    def get_adjustable_range(self):
        """
        返回可调整的路线片段（不含首尾食堂）

        例如 full_route = [食堂, A, B, C, D, 食堂]
        frozen_index = 1（A 已锁定）
        返回的可调整 indices = [2, 3, 4]，对应 [B, C, D]
        """
        # 可调整范围：frozen_index + 1 到 倒数第二个（最后一个是回食堂）
        start = self.frozen_index + 1
        end = len(self.full_route) - 1  # 不含最后的食堂
        return list(range(start, end))

    def advance_frozen(self):
        """
        骑手完成当前配送点，冻结指针前进一步
        """
        max_idx = len(self.full_route) - 2  # 最多冻结到倒数第二个
        if self.frozen_index < max_idx:
            self.frozen_index += 1

    def to_dict(self):
        return {
            'courier_id': self.courier_id,
            'full_route': self.full_route,
            'order_db_ids': self.order_db_ids,
            'frozen_index': self.frozen_index,
            'adjustable_count': len(self.get_adjustable_range()),
            'distance': round(self.distance, 2),
        }


class DynamicScheduler:
    """
    动态调度器（全局单例）

    使用方式：
      1. 批次优化完成后，调用 init_from_batch() 载入骑手路线
      2. 新订单到达时，调用 insert_order() 快速插入
      3. 前端轮询 get_state() 获取最新路线
      4. 后台线程定期调用 periodic_reoptimize() 全局微调
    """

    def __init__(self):
        self.couriers = {}          # {courier_id: CourierState}
        self.batch_id = None        # 当前活跃批次
        self.canteen_node_index = None
        self.is_active = False      # 调度器是否在运行
        self._lock = threading.Lock()
        self._bg_thread = None
        self._stop_event = threading.Event()

        # 统计
        self.stats = {
            'total_inserted': 0,        # 动态插入的订单数
            'total_reoptimize': 0,      # 全局微调次数
            'last_reoptimize_time': None
        }

    # ============================================================
    # ① 初始化：从批次优化结果载入状态
    # ============================================================

    def init_from_batch(self, batch_id, courier_details, canteen_node_index):
        """
        从一次批次优化的结果初始化调度器

        参数：
          batch_id: 当前批次 ID
          courier_details: {
            1: {
              'orders': [5, 12, 8],           # node_index 列表
              'order_db_ids': [101, 102, 103], # 数据库订单 ID
              'distance': 1234.5
            },
            2: { ... }
          }
          canteen_node_index: 食堂节点编号
        """
        with self._lock:
            self.couriers = {}
            self.batch_id = batch_id
            self.canteen_node_index = canteen_node_index

            for cid_str, detail in courier_details.items():
                cid = int(cid_str)
                orders = detail.get('orders', [])
                db_ids = detail.get('order_db_ids', [])

                if not orders:
                    continue

                # full_route: [食堂, 订单1, 订单2, ..., 食堂]
                full_route = [canteen_node_index] + list(orders) + [canteen_node_index]
                # order_db_ids: [None, id1, id2, ..., None]
                order_db_ids = [None] + list(db_ids) + [None]

                self.couriers[cid] = CourierState(
                    courier_id=cid,
                    full_route=full_route,
                    order_db_ids=order_db_ids,
                    distance=detail.get('distance', 0)
                )

            self.is_active = True
            self.stats['total_inserted'] = 0
            self.stats['total_reoptimize'] = 0

            print(f"📡 动态调度器已初始化：批次#{batch_id}，"
                  f"{len(self.couriers)}个骑手")

    # ============================================================
    # ② 核心：插入法 — 新订单快速分配
    # ============================================================

    def insert_order(self, order_node_index, order_db_id, distance_func):
        """
        用插入法把新订单分配到最佳骑手的最佳位置

        算法：
          遍历每个骑手的可调整路线段，
          把新订单尝试插入每个位置，
          选择"增加距离最小"的方案。

        参数：
          order_node_index: 新订单目的地节点编号 (1-based)
          order_db_id:      新订单数据库 ID
          distance_func:    距离计算函数 distance_func(from_idx, to_idx) → float
                           接受两个 node_index，返回距离（米）

        返回：
          {
            'courier_id': 分配到的骑手编号,
            'position': 插入位置,
            'added_distance': 增加的距离,
            'new_route': 新路线
          }
        """
        if not self.is_active or not self.couriers:
            return None

        with self._lock:
            best_result = None
            best_added = float('inf')

            for cid, state in self.couriers.items():
                adjustable = state.get_adjustable_range()

                # 如果没有可调整的位置，就插在回食堂之前
                if not adjustable:
                    # 插在最后一个（食堂）前面
                    insert_pos = len(state.full_route) - 1
                    prev_node = state.full_route[insert_pos - 1]
                    next_node = state.full_route[insert_pos]

                    old_dist = distance_func(prev_node, next_node)
                    new_dist = (distance_func(prev_node, order_node_index) +
                                distance_func(order_node_index, next_node))
                    added = new_dist - old_dist

                    if added < best_added:
                        best_added = added
                        best_result = {
                            'courier_id': cid,
                            'position': insert_pos,
                            'added_distance': added
                        }
                else:
                    # 遍历每个可插入位置
                    # 可插入的位置：adjustable 的每个位置之前，以及最后一个 adjustable 之后
                    for pos in adjustable:
                        prev_node = state.full_route[pos - 1]
                        next_node = state.full_route[pos]

                        old_dist = distance_func(prev_node, next_node)
                        new_dist = (distance_func(prev_node, order_node_index) +
                                    distance_func(order_node_index, next_node))
                        added = new_dist - old_dist

                        if added < best_added:
                            best_added = added
                            best_result = {
                                'courier_id': cid,
                                'position': pos,
                                'added_distance': added
                            }

                    # 也尝试插在最后一个可调整位置之后（回食堂之前）
                    last_adj = adjustable[-1]
                    insert_pos = last_adj + 1
                    if insert_pos < len(state.full_route):
                        prev_node = state.full_route[last_adj]
                        next_node = state.full_route[insert_pos]

                        old_dist = distance_func(prev_node, next_node)
                        new_dist = (distance_func(prev_node, order_node_index) +
                                    distance_func(order_node_index, next_node))
                        added = new_dist - old_dist

                        if added < best_added:
                            best_added = added
                            best_result = {
                                'courier_id': cid,
                                'position': insert_pos,
                                'added_distance': added
                            }

            if best_result is None:
                return None

            # 执行插入
            cid = best_result['courier_id']
            pos = best_result['position']
            state = self.couriers[cid]

            state.full_route.insert(pos, order_node_index)
            state.order_db_ids.insert(pos, order_db_id)
            state.distance += best_added

            self.stats['total_inserted'] += 1

            best_result['new_route'] = list(state.full_route)
            best_result['added_distance'] = round(best_added, 2)

            print(f"📌 动态插入：订单#{order_db_id} → 骑手{cid} "
                  f"位置{pos}，增加{best_added:.1f}米")

            return best_result

    # ============================================================
    # ③ 模拟骑手前进（推进冻结指针）
    # ============================================================

    def advance_courier(self, courier_id):
        """
        骑手完成当前配送点，冻结指针 +1

        这个方法应该在订单状态从 delivering → delivered 时调用，
        或者由前端的"模拟前进"按钮触发。
        """
        with self._lock:
            if courier_id in self.couriers:
                self.couriers[courier_id].advance_frozen()
                return True
        return False

    def advance_all(self):
        """所有骑手冻结指针前进一步"""
        with self._lock:
            for state in self.couriers.values():
                state.advance_frozen()

    # ============================================================
    # ④ 定期全局微调（短程 GA）
    # ============================================================

    def periodic_reoptimize(self, distance_func):
        """
        对每个骑手的未冻结路线段做一轮短程 GA 微调

        策略：
          - 只取可调整部分（冻结后的）
          - 用小种群 + 少代数的 GA（50种群 × 30代）
          - 如果可调整段 ≤ 2 个点就跳过（没什么好优化的）
        """
        from app.delivery.ga_optimizer import GeneticAlgorithmTSPWith2Opt

        if not self.is_active or not self.couriers:
            return

        with self._lock:
            for cid, state in self.couriers.items():
                adjustable = state.get_adjustable_range()
                if len(adjustable) <= 2:
                    continue  # 太少了，没必要优化

                # 取出可调整段的 node_index
                adj_nodes = [state.full_route[i] for i in adjustable]

                # 构建小规模距离矩阵
                n = len(adj_nodes)
                matrix = np.zeros((n, n))
                for i in range(n):
                    for j in range(i + 1, n):
                        d = distance_func(adj_nodes[i], adj_nodes[j])
                        matrix[i][j] = d
                        matrix[j][i] = d

                # 短程 GA：小种群 + 少代数
                ga = GeneticAlgorithmTSPWith2Opt(
                    matrix,
                    population_size=50,
                    generations=30,
                    mutation_rate=0.3,
                    crossover_rate=0.8,
                    use_2opt=True,
                    apply_2opt_interval=5
                )
                best_route, _ = ga.solve()

                # 将优化结果映射回原路线
                new_adj_nodes = [adj_nodes[i] for i in best_route]
                new_adj_db_ids = [state.order_db_ids[adjustable[i]]
                                  for i in best_route]

                for k, idx in enumerate(adjustable):
                    state.full_route[idx] = new_adj_nodes[k]
                    state.order_db_ids[idx] = new_adj_db_ids[k]

                # 重新计算总距离
                total = 0
                for i in range(len(state.full_route) - 1):
                    total += distance_func(
                        state.full_route[i], state.full_route[i + 1]
                    )
                state.distance = total

            self.stats['total_reoptimize'] += 1
            self.stats['last_reoptimize_time'] = time.strftime('%H:%M:%S')
            print(f"🔄 定期微调完成（第{self.stats['total_reoptimize']}次）")

    # ============================================================
    # ⑤ 后台线程管理
    # ============================================================

    def start_background(self, app, interval_seconds=60):
        """
        启动后台定期微调线程

        参数：
          app: Flask app 实例（后台线程需要应用上下文）
          interval_seconds: 微调间隔（默认 60 秒）
        """
        if self._bg_thread and self._bg_thread.is_alive():
            return  # 已经在跑了

        self._stop_event.clear()

        def _run():
            with app.app_context():
                while not self._stop_event.is_set():
                    self._stop_event.wait(interval_seconds)
                    if self._stop_event.is_set():
                        break
                    if self.is_active:
                        try:
                            dist_func = self._get_distance_func()
                            if dist_func:
                                self.periodic_reoptimize(dist_func)
                        except Exception as e:
                            print(f"⚠️ 定期微调出错: {e}")

        self._bg_thread = threading.Thread(target=_run, daemon=True)
        self._bg_thread.start()
        print(f"⏱️ 后台微调线程已启动，间隔 {interval_seconds} 秒")

    def stop_background(self):
        """停止后台线程"""
        self._stop_event.set()
        self.is_active = False

    def _get_distance_func(self):
        """
        获取距离计算函数（基于路网 Dijkstra）

        返回一个 distance_func(node_idx_a, node_idx_b) → float
        """
        from app.delivery.graph_service import graph_service
        import networkx as nx

        try:
            graph = graph_service.get_graph()
            node_list = graph_service.get_node_list()
        except Exception:
            return None

        def calc(idx_a, idx_b):
            """给定两个 node_index(1-based)，返回最短路径距离"""
            if idx_a == idx_b:
                return 0
            try:
                real_a = node_list[idx_a - 1]
                real_b = node_list[idx_b - 1]
                path = nx.shortest_path(graph, real_a, real_b, weight='length')
                return sum(
                    graph[path[k]][path[k + 1]][0]['length']
                    for k in range(len(path) - 1)
                )
            except (nx.NetworkXNoPath, IndexError):
                return float('inf')

        return calc

    # ============================================================
    # ⑥ 状态查询
    # ============================================================

    def get_state(self):
        """返回完整调度状态（给前端用）"""
        with self._lock:
            return {
                'is_active': self.is_active,
                'batch_id': self.batch_id,
                'couriers': {
                    cid: state.to_dict()
                    for cid, state in self.couriers.items()
                },
                'stats': dict(self.stats),
            }

    def get_courier_routes_for_map(self, positions_func):
        """
        返回每个骑手的路线坐标（给前端地图绘制用）

        参数：
          positions_func: 函数 positions_func(node_index) → {'lat': ..., 'lon': ...}
        """
        with self._lock:
            result = {}
            for cid, state in self.couriers.items():
                coords = []
                for node_idx in state.full_route:
                    pos = positions_func(node_idx)
                    if pos:
                        coords.append([pos['lat'], pos['lon']])
                result[cid] = {
                    'route_coords': coords,
                    'orders': [
                        node_idx for node_idx in state.full_route
                        if node_idx != self.canteen_node_index
                    ],
                    'order_db_ids': [
                        db_id for db_id in state.order_db_ids
                        if db_id is not None
                    ],
                    'frozen_index': state.frozen_index,
                    'distance': round(state.distance, 2),
                }
            return result

    def reset(self):
        """重置调度器"""
        with self._lock:
            self.stop_background()
            self.couriers = {}
            self.batch_id = None
            self.is_active = False
            self.stats = {
                'total_inserted': 0,
                'total_reoptimize': 0,
                'last_reoptimize_time': None
            }


# ★ 全局单例
scheduler = DynamicScheduler()