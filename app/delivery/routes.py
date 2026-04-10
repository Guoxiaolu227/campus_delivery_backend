"""
配送业务 API 路由
★ 阶段2重写：新增订单管理 + 批次优化

API 一览：
  GET  /delivery/graph_info          — 获取路网信息（不变）
  GET  /delivery/nodes               — 获取节点坐标（不变）
  GET  /delivery/pois                — POI 列表（不变）
  POST /delivery/pois                — 创建 POI（不变）
  ...其他 POI 路由（不变）...

  ★ 新增/重写的订单相关路由：
  POST /delivery/orders/create       — 手动下单
  POST /delivery/orders/random       — 随机生成订单(写库)
  GET  /delivery/orders              — 订单列表
  POST /delivery/orders/<id>/status  — 推进订单状态
  POST /delivery/orders/batch_status — 批量推进状态
  POST /delivery/optimize            — 批次优化（从数据库读→优化→写回）
  GET  /delivery/batches             — 批次列表
"""

import json
import networkx as nx
from flask import jsonify, request, current_app
from app.delivery import bp
from app.delivery.graph_service import graph_service
from app.delivery.order_service import order_service
from app.delivery.ga_optimizer import GeneticAlgorithmTSPWith2Opt
from app.delivery.poi_service import poi_service


# ================================================================
# 路网信息（不变）
# ================================================================

@bp.route('/graph_info', methods=['GET'])
def get_graph_info():
    try:
        graph = graph_service.get_graph()
        return jsonify({
            'success': True,
            'data': {
                'node_count': len(graph.nodes()),
                'edge_count': len(graph.edges()),
                'school_name': current_app.config['SCHOOL_NAME'],
                'center_lat': current_app.config['SCHOOL_CENTER_LAT'],
                'center_lon': current_app.config['SCHOOL_CENTER_LON'],
                'radius': current_app.config['CAMPUS_RADIUS']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/nodes', methods=['GET'])
def get_nodes():
    try:
        positions = graph_service.get_node_positions()
        node_list = graph_service.get_node_list()
        nodes = [{'id': int(node), 'lat': positions[node]['lat'],
                  'lon': positions[node]['lon'], 'index': i + 1}
                 for i, node in enumerate(node_list)]
        return jsonify({'success': True, 'data': nodes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================================================
# ★ 阶段2新增/重写：订单管理
# ================================================================

@bp.route('/orders/create', methods=['POST'])
def create_order():
    """
    手动下单

    请求 JSON（方式1 — 选择已知 POI）:
      {"to_poi_id": 3}

    请求 JSON（方式2 — 地图点击任意位置）:
      {"to_node_index": 25, "address": "西苑路口"}
    """
    try:
        data = request.get_json()
        order = order_service.create_order(
            to_poi_id=data.get('to_poi_id'),
            to_node_index=data.get('to_node_index'),
            address=data.get('address', '')
        )
        return jsonify({'success': True, 'data': order})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/orders/random', methods=['POST'])
def generate_orders():
    """
    随机生成订单（写入数据库）

    请求 JSON:
      {"num_orders": 10}

    和旧版的区别：
      旧版只返回内存数据
      新版每个订单都 INSERT 到 orders 表
    """
    try:
        data = request.get_json()
        num_orders = data.get('num_orders', 10)
        orders = order_service.generate_random_orders(num_orders)

        # 额外返回坐标（前端地图标注用）
        positions = graph_service.get_node_positions()
        node_list = graph_service.get_node_list()
        for o in orders:
            idx = o['to_node_index']
            if 1 <= idx <= len(node_list):
                real_node = node_list[idx - 1]
                pos = positions[real_node]
                o['lat'] = pos['lat']
                o['lon'] = pos['lon']

        return jsonify({'success': True, 'data': {
            'orders': orders,
            'count': len(orders)
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/orders', methods=['GET'])
def get_orders():
    """
    获取订单列表

    查询参数：
      status   — 按状态筛选（pending/accepted/delivering/delivered）
      batch_id — 按批次筛选

    示例：GET /delivery/orders?status=pending
    """
    try:
        status = request.args.get('status')
        batch_id = request.args.get('batch_id', type=int)
        orders = order_service.get_orders(status=status, batch_id=batch_id)

        # 附加坐标
        positions = graph_service.get_node_positions()
        node_list = graph_service.get_node_list()
        for o in orders:
            idx = o['to_node_index']
            if 1 <= idx <= len(node_list):
                real_node = node_list[idx - 1]
                pos = positions[real_node]
                o['lat'] = pos['lat']
                o['lon'] = pos['lon']

        # 统计各状态数量
        stats = {}
        for o in orders:
            s = o['status']
            stats[s] = stats.get(s, 0) + 1

        return jsonify({'success': True, 'data': {
            'orders': orders,
            'total': len(orders),
            'stats': stats,
            'pending_count': order_service.get_pending_count()
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/orders/<int:order_id>/status', methods=['POST'])
def update_order_status(order_id):
    """
    推进单个订单的状态

    请求 JSON:
      {"status": "picked_up"}
    """
    try:
        data = request.get_json()
        new_status = data.get('status')
        order = order_service.transition_status(order_id, new_status)
        return jsonify({'success': True, 'data': order})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/orders/batch_status', methods=['POST'])
def batch_update_status():
    """
    批量推进状态（整个批次一键推进）

    请求 JSON:
      {"batch_id": 1, "status": "picked_up"}
    """
    try:
        data = request.get_json()
        batch_id = data.get('batch_id')
        new_status = data.get('status')
        updated = order_service.batch_transition(batch_id, new_status)
        return jsonify({'success': True, 'data': {'updated': updated}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================================================
# ★ 阶段2重写：批次优化（从数据库读→优化→写回）
# ================================================================

@bp.route('/optimize', methods=['POST'])
def optimize_route():
    """
    批次优化（★ 阶段2核心改造）

    改造前：前端传 order_nodes 列表 → 后端内存计算 → 返回
    改造后：
      1. 从数据库读取所有 pending 订单
      2. 创建 Batch（批次），订单状态 pending → accepted
      3. 根据订单的 to_node_index 构建距离矩阵
      4. GA+2-opt 优化
      5. 轮转分配骑手
      6. 结果写回数据库
      7. 返回完整结果给前端

    请求 JSON:
      {
        "num_couriers": 4,
        "ga_params": { ... }
      }

    注意：不再需要前端传 order_nodes/order_ids了！
    """
    try:
        data = request.get_json()
        num_couriers = data.get('num_couriers', 4)
        ga_params = data.get('ga_params', {})

        # ---- 步骤1：创建批次，从数据库取 pending 订单 ----
        batch, pending_orders = order_service.create_batch(num_couriers, ga_params)

        # ---- 步骤2：准备算法输入 ----
        node_list = graph_service.get_node_list()
        canteen_id = current_app.config['CANTEEN_NODE_ID']
        canteen_node = node_list[canteen_id - 1]
        positions = graph_service.get_node_positions()

        # 构造节点列表：[食堂, 订单1目的地, 订单2目的地, ...]
        order_nodes = []
        order_ids = []
        order_db_ids = []  # 数据库中的订单 ID，用于后续关联
        for o in pending_orders:
            real_node = node_list[o.to_node_index - 1]
            order_nodes.append(real_node)
            order_ids.append(o.to_node_index)
            order_db_ids.append(o.id)

        all_locations = [canteen_node] + order_nodes
        location_ids = [canteen_id] + order_ids

        # ---- 步骤3：距离矩阵 ----
        distance_matrix = graph_service.compute_distance_matrix(all_locations)

        # ---- 步骤4：GA + 2-opt ----
        ga = GeneticAlgorithmTSPWith2Opt(
            distance_matrix,
            population_size=ga_params.get('population_size', 200),
            generations=ga_params.get('generations', 500),
            mutation_rate=ga_params.get('mutation_rate', 0.2),
            crossover_rate=ga_params.get('crossover_rate', 0.8),
            use_2opt=ga_params.get('use_2opt', True),
            apply_2opt_interval=ga_params.get('apply_2opt_interval', 10)
        )
        optimal_route, optimal_distance = ga.solve()

        # ---- 步骤5：分配骑手 ----
        courier_assignments = order_service.allocate_couriers(
            optimal_route, all_locations, location_ids,
            num_couriers, canteen_node, canteen_id
        )

        # ---- 步骤6：构造路线详情 + 写回数据库 ----
        graph = graph_service.get_graph()
        courier_details = {}

        for cid in range(1, num_couriers + 1):
            loc_indices = courier_assignments[cid]
            if not loc_indices:
                courier_details[cid] = {
                    'orders': [], 'order_db_ids': [],
                    'distance': 0, 'route_coords': []
                }
                continue

            courier_locs = [canteen_node] + \
                [all_locations[idx] for idx in loc_indices] + [canteen_node]

            c_distance = 0
            route_coords = []

            for k in range(len(courier_locs) - 1):
                try:
                    path = nx.shortest_path(
                        graph, courier_locs[k], courier_locs[k + 1],
                        weight='length'
                    )
                    seg_dist = sum(
                        graph[path[m]][path[m + 1]][0]['length']
                        for m in range(len(path) - 1)
                    )
                    c_distance += seg_dist
                    for node in path:
                        pos = positions[node]
                        route_coords.append([pos['lat'], pos['lon']])
                except nx.NetworkXNoPath:
                    pass

            # 这个骑手负责的订单在 order_db_ids 中的下标
            # loc_indices 中的值是 all_locations 中的下标（1-based 起因为0是食堂）
            this_courier_order_db_ids = [order_db_ids[idx - 1] for idx in loc_indices]

            # 写回数据库：给这些订单分配骑手编号
            order_service.assign_courier_to_orders(
                batch.id, cid, this_courier_order_db_ids
            )

            courier_details[cid] = {
                'orders': [location_ids[idx] for idx in loc_indices],
                'order_db_ids': this_courier_order_db_ids,
                'distance': round(c_distance, 2),
                'route_coords': route_coords
            }

        # 保存优化结果到批次
        order_service.save_batch_result(batch, optimal_distance, {
            'optimal_route_ids': [location_ids[i] for i in optimal_route],
            'courier_details': {str(k): v for k, v in courier_details.items()}
        })

        # 最优路线坐标
        optimal_coords = []
        route_node_list = [all_locations[i] for i in optimal_route]
        for node in route_node_list:
            pos = positions[node]
            optimal_coords.append([pos['lat'], pos['lon']])

        return jsonify({
            'success': True,
            'data': {
                'batch_id': batch.id,
                'order_count': len(pending_orders),
                'optimal_distance': round(optimal_distance, 2),
                'optimal_route_ids': [location_ids[i] for i in optimal_route],
                'optimal_coords': optimal_coords,
                'convergence': ga.best_distances,
                'courier_details': courier_details,
                'canteen': {
                    'lat': positions[canteen_node]['lat'],
                    'lon': positions[canteen_node]['lon']
                }
            }
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/batches', methods=['GET'])
def get_batches():
    """获取所有批次"""
    try:
        batches = order_service.get_batches()
        return jsonify({'success': True, 'data': batches})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================================================
# POI 路由（阶段1已有，完全不改）
# ================================================================

@bp.route('/pois', methods=['GET'])
def get_pois():
    try:
        poi_type = request.args.get('type', None)
        active_only = request.args.get('all', 'false') != 'true'
        pois = poi_service.get_all_pois(poi_type=poi_type, active_only=active_only)
        stats = {}
        for p in pois:
            t = p['poi_type']
            stats[t] = stats.get(t, 0) + 1
        return jsonify({
            'success': True,
            'data': {'pois': pois, 'total': len(pois), 'stats': stats}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pois', methods=['POST'])
def create_poi():
    try:
        data = request.get_json()
        poi = poi_service.create_poi(
            name=data['name'], poi_type=data['poi_type'],
            node_index=data.get('node_index'), lat=data.get('lat'),
            lon=data.get('lon'), description=data.get('description', ''),
            capacity=data.get('capacity', 0)
        )
        return jsonify({'success': True, 'data': poi})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pois/<int:poi_id>', methods=['PUT'])
def update_poi(poi_id):
    try:
        data = request.get_json()
        poi = poi_service.update_poi(poi_id, **data)
        return jsonify({'success': True, 'data': poi})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pois/<int:poi_id>', methods=['DELETE'])
def delete_poi(poi_id):
    try:
        result = poi_service.delete_poi(poi_id)
        return jsonify({'success': True, 'data': result})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pois/init', methods=['POST'])
def init_pois():
    try:
        added = poi_service.init_pois()
        pois = poi_service.get_all_pois()
        return jsonify({
            'success': True,
            'data': {'pois': pois, 'total': len(pois), 'added': added}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/nearest_node', methods=['GET'])
def find_nearest_node():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        result = graph_service.find_nearest_node_info(lat, lon)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500