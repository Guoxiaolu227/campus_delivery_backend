"""
订单管理服务（★ 阶段2重写）

核心变化：
  旧版：订单只是一组内存中的数字，用完就丢
  新版：订单持久化到数据库，有完整生命周期

提供的功能：
  1. create_order()          — 手动下单（从 POI 选起点终点）
  2. generate_random_orders() — 随机批量下单（测试用，也写库）
  3. get_pending_orders()     — 获取所有待处理订单
  4. transition_status()      — 订单状态流转（状态机）
  5. create_batch_and_optimize() — 创建批次并执行 GA 优化
  6. allocate_couriers()      — 骑手分配（保留原逻辑）
"""

import json
import random
from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import (
    Order, Batch, Courier, POI,
    ORDER_PENDING, ORDER_ACCEPTED, ORDER_PICKED_UP,
    ORDER_DELIVERING, ORDER_DELIVERED,
    STATUS_TRANSITIONS, STATUS_LABELS
)
from app.delivery.graph_service import graph_service


class OrderService:
    """订单管理服务"""

    # ============================================================
    # ① 手动下单
    # ============================================================

    def create_order(self, to_poi_id=None, to_node_index=None, address=''):
        """
        创建一个订单（手动下单）

        参数说明：
          to_poi_id:     目的地 POI 的 ID（如果用户从下拉框选了一个已知地点）
          to_node_index: 目的地节点编号（如果用户在地图上点击了任意位置）
          address:       地址描述文字

        二选一逻辑：
          - 传了 to_poi_id → 从 POI 表查 node_index
          - 传了 to_node_index → 直接使用

        食堂（起点）固定为嘉慧园食堂（系统中唯一的 canteen 类型 POI）。
        """
        # 查找食堂
        canteen = POI.query.filter_by(poi_type='canteen', is_active=True).first()
        from_poi_id = canteen.id if canteen else None

        # 确定目的地
        if to_poi_id:
            poi = POI.query.get(to_poi_id)
            if not poi:
                raise ValueError(f"目的地 POI ID={to_poi_id} 不存在")
            to_node_index = poi.node_index
            if not address:
                address = poi.name
        elif to_node_index:
            # 检查 node_index 合法性
            node_list = graph_service.get_node_list()
            if to_node_index < 1 or to_node_index > len(node_list):
                raise ValueError(f"节点编号 {to_node_index} 超出范围")
            if not address:
                address = f'节点 #{to_node_index}'
        else:
            raise ValueError("必须提供 to_poi_id 或 to_node_index")

        order = Order(
            from_poi_id=from_poi_id,
            to_poi_id=to_poi_id,
            to_node_index=to_node_index,
            address=address,
            status=ORDER_PENDING
        )
        db.session.add(order)
        db.session.commit()
        return order.to_dict()

    # ============================================================
    # ② 随机批量下单（测试用，但也写入数据库）
    # ============================================================

    def generate_random_orders(self, num_orders):
        """
        随机生成订单并写入数据库

        和旧版的区别：
          旧版只返回内存数据，用完即弃
          新版每个订单都会写入 orders 表，状态为 pending
        """
        node_list = graph_service.get_node_list()
        if num_orders > len(node_list):
            raise ValueError(f"订单数量({num_orders})超过可用节点数({len(node_list)})")

        # 查找食堂
        canteen = POI.query.filter_by(poi_type='canteen', is_active=True).first()
        canteen_id = current_app.config['CANTEEN_NODE_ID']

        # 随机抽取节点（排除食堂节点）
        candidates = [i + 1 for i in range(len(node_list)) if (i + 1) != canteen_id]
        if num_orders > len(candidates):
            num_orders = len(candidates)
        selected_indices = random.sample(candidates, num_orders)

        orders = []
        for idx in selected_indices:
            # 检查是否有对应的 POI
            poi = POI.query.filter_by(node_index=idx, is_active=True).first()

            order = Order(
                from_poi_id=canteen.id if canteen else None,
                to_poi_id=poi.id if poi else None,
                to_node_index=idx,
                address=poi.name if poi else f'节点 #{idx}',
                status=ORDER_PENDING
            )
            db.session.add(order)
            orders.append(order)

        db.session.commit()

        return [o.to_dict() for o in orders]

    # ============================================================
    # ③ 查询订单
    # ============================================================

    def get_orders(self, status=None, batch_id=None):
        """
        查询订单列表

        参数：
          status:   按状态筛选（pending/accepted/delivering/delivered）
          batch_id: 按批次筛选
        """
        query = Order.query
        if status:
            query = query.filter_by(status=status)
        if batch_id:
            query = query.filter_by(batch_id=batch_id)
        return [o.to_dict() for o in query.order_by(Order.created_at.desc()).all()]

    def get_pending_count(self):
        """获取待处理订单数量"""
        return Order.query.filter_by(status=ORDER_PENDING).count()

    # ============================================================
    # ④ 状态流转（状态机核心）
    # ============================================================

    def transition_status(self, order_id, new_status):
        """
        订单状态流转

        核心逻辑（状态机规则）：
          pending → accepted       （被纳入批次，分配了骑手）
          accepted → picked_up     （骑手到达食堂取餐）
          picked_up → delivering   （骑手出发配送）
          delivering → delivered   （骑手送达目的地）

        违反规则时抛出异常。例如不能从 pending 直接跳到 delivered。

        每次状态变化都记录对应的时间戳，方便后续统计：
          "这个订单从下单到送达一共花了多少分钟？"
        """
        order = Order.query.get(order_id)
        if not order:
            raise ValueError(f"订单 {order_id} 不存在")

        allowed = STATUS_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"非法状态转换: {order.status} → {new_status}。"
                f"允许的下一状态: {allowed}"
            )

        # 更新状态
        order.status = new_status

        # 记录时间戳
        now = datetime.utcnow()
        if new_status == ORDER_ACCEPTED:
            order.accepted_at = now
        elif new_status == ORDER_PICKED_UP:
            order.picked_up_at = now
        elif new_status == ORDER_DELIVERING:
            order.delivering_at = now
        elif new_status == ORDER_DELIVERED:
            order.delivered_at = now

        db.session.commit()
        return order.to_dict()

    def batch_transition(self, batch_id, new_status):
        """
        批量状态流转：把一个批次的所有订单推进到下一状态

        用途：模拟配送过程
          例如点击"全部取餐" → 该批次所有 accepted 订单变为 picked_up
        """
        orders = Order.query.filter_by(batch_id=batch_id).all()
        updated = 0
        for order in orders:
            allowed = STATUS_TRANSITIONS.get(order.status, [])
            if new_status in allowed:
                order.status = new_status
                now = datetime.utcnow()
                if new_status == ORDER_ACCEPTED:
                    order.accepted_at = now
                elif new_status == ORDER_PICKED_UP:
                    order.picked_up_at = now
                elif new_status == ORDER_DELIVERING:
                    order.delivering_at = now
                elif new_status == ORDER_DELIVERED:
                    order.delivered_at = now
                updated += 1
        db.session.commit()
        return updated

    # ============================================================
    # ⑤ 批次管理 + 优化
    # ============================================================

    def create_batch(self, num_couriers, ga_params):
        """
        创建配送批次

        逻辑：
          1. 从数据库取出所有 pending 订单
          2. 创建一个 Batch 记录
          3. 把这些订单关联到 Batch（设置 batch_id）
          4. 把订单状态从 pending → accepted
          5. 返回 Batch 和订单列表，供后续 GA 优化使用

        参数：
          num_couriers: 骑手数量
          ga_params: GA 算法参数字典
        """
        pending_orders = Order.query.filter_by(status=ORDER_PENDING)\
            .order_by(Order.created_at).all()

        if not pending_orders:
            raise ValueError("没有待处理的订单")

        # 创建批次
        batch = Batch(
            order_count=len(pending_orders),
            courier_count=num_couriers,
            ga_params_json=json.dumps(ga_params, ensure_ascii=False)
        )
        db.session.add(batch)
        db.session.flush()  # 获取 batch.id

        # 关联订单并更新状态
        now = datetime.utcnow()
        for order in pending_orders:
            order.batch_id = batch.id
            order.status = ORDER_ACCEPTED
            order.accepted_at = now

        db.session.commit()

        return batch, pending_orders

    def save_batch_result(self, batch, total_distance, result_json):
        """优化完成后保存结果到批次"""
        batch.total_distance = total_distance
        batch.optimal_route_json = json.dumps(result_json, ensure_ascii=False)
        batch.status = 'optimized'
        db.session.commit()

    def assign_courier_to_orders(self, batch_id, courier_id_int, order_ids):
        """把一组订单分配给一个骑手"""
        for oid in order_ids:
            order = Order.query.get(oid)
            if order and order.batch_id == batch_id:
                order.courier_id = courier_id_int

        db.session.commit()

    def get_batches(self):
        """获取所有批次（按时间倒序）"""
        return [b.to_dict() for b in Batch.query.order_by(Batch.created_at.desc()).all()]

    # ============================================================
    # ⑥ 骑手分配（保留原有轮转逻辑）
    # ============================================================

    def allocate_couriers(self, optimal_route, all_locations, location_ids,
                          num_couriers, canteen_node, canteen_id):
        """
        根据 GA 最优路线轮转分配骑手（和原来完全相同）
        """
        order_location_indices = []
        for idx in optimal_route:
            if all_locations[idx] != canteen_node:
                order_location_indices.append(idx)

        courier_assignments = {}
        for cid in range(1, num_couriers + 1):
            courier_assignments[cid] = []

        for step, loc_idx in enumerate(order_location_indices):
            cid = (step % num_couriers) + 1
            courier_assignments[cid].append(loc_idx)

        return courier_assignments
    # ============================================================
    # ⑦ ★ 阶段4新增：动态调度相关
    # ============================================================

    def create_dynamic_order(self, to_poi_id=None, to_node_index=None,
                             address='', batch_id=None):
        """
        创建一个"动态订单"——在骑手出发后新增的订单

        和 create_order() 的区别：
          - 状态直接设为 accepted（不需要等下一次批次优化）
          - 记录 insert_batch_id，标记为动态插入
          - 关联到当前活跃批次
        """
        canteen = POI.query.filter_by(poi_type='canteen', is_active=True).first()
        from_poi_id = canteen.id if canteen else None

        if to_poi_id:
            poi = POI.query.get(to_poi_id)
            if not poi:
                raise ValueError(f"目的地 POI ID={to_poi_id} 不存在")
            to_node_index = poi.node_index
            if not address:
                address = poi.name
        elif to_node_index:
            node_list = graph_service.get_node_list()
            if to_node_index < 1 or to_node_index > len(node_list):
                raise ValueError(f"节点编号 {to_node_index} 超出范围")
            if not address:
                address = f'节点 #{to_node_index}'
        else:
            raise ValueError("必须提供 to_poi_id 或 to_node_index")

        order = Order(
            from_poi_id=from_poi_id,
            to_poi_id=to_poi_id,
            to_node_index=to_node_index,
            address=address,
            status=ORDER_ACCEPTED,          # 直接 accepted
            batch_id=batch_id,
            insert_batch_id=batch_id,       # 标记为动态插入
            accepted_at=datetime.utcnow()
        )
        db.session.add(order)
        db.session.commit()
        return order

    def freeze_order(self, order_id):
        """标记订单为已冻结（骑手已经过该配送点）"""
        order = Order.query.get(order_id)
        if order:
            order.is_frozen = True
            db.session.commit()
        return order


# 全局单例
order_service = OrderService()