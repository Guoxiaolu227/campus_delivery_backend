"""
配送业务 API 路由（对应 daima.py 的所有步骤的 Web 化）

每个路由对应前端的一个操作按钮：
1. GET  /delivery/graph_info     — 获取路网信息
2. POST /delivery/generate_orders — 生成随机订单
3. POST /delivery/optimize       — 运行 GA+2-opt 优化
4. GET  /delivery/nodes          — 获取所有节点坐标（用于地图绘制）
"""

import json
import networkx as nx
from flask import jsonify, request, current_app
from app.delivery import bp
from app.delivery.graph_service import graph_service
from app.delivery.order_service import order_service
from app.delivery.ga_optimizer import GeneticAlgorithmTSPWith2Opt


@bp.route('/graph_info', methods=['GET'])
def get_graph_info():
    """
    获取路网基本信息

    对应 daima.py 中打印路网节点/边数量的部分

    返回 JSON:
        {
            "node_count": 节点数,
            "edge_count": 边数,
            "school_name": 学校名称
        }
    """
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
    """
    获取所有节点坐标（前端地图绑定用）

    返回 JSON:
        {
            "nodes": [
                {"id": 节点ID, "lat": 纬度, "lon": 经度, "index": 1-based编号},
                ...
            ]
        }
    """
    try:
        positions = graph_service.get_node_positions()
        node_list = graph_service.get_node_list()

        nodes = []
        for i, node in enumerate(node_list):
            pos = positions[node]
            nodes.append({
                'id': int(node),
                'lat': pos['lat'],
                'lon': pos['lon'],
                'index': i + 1  # 1-based 编号
            })

        return jsonify({'success': True, 'data': nodes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/generate_orders', methods=['POST'])
def generate_orders():
    """
    生成随机订单

    请求 JSON:
        {"num_orders": 40}

    对应 daima.py 中的：
        order_nodes = random.sample(node_list, NUM_ORDERS)
    """
    try:
        data = request.get_json()
        num_orders = data.get('num_orders', 40)

        result = order_service.generate_random_orders(num_orders)
        node_list = graph_service.get_node_list()
        positions = graph_service.get_node_positions()

        # 构造订单详情（包含坐标，方便前端在地图上标注）
        orders_detail = []
        for i, node in enumerate(result['order_nodes']):
            pos = positions[node]
            orders_detail.append({
                'order_id': i + 1,
                'node_id': result['order_ids'][i],
                'real_node': int(node),
                'lat': pos['lat'],
                'lon': pos['lon']
            })

        return jsonify({
            'success': True,
            'data': {
                'num_orders': num_orders,
                'orders': orders_detail,
                'order_nodes': [int(n) for n in result['order_nodes']],
                'order_ids': result['order_ids']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/optimize', methods=['POST'])
def optimize_route():
    """
    运行 GA+2-opt 路径优化（核心接口）

    请求 JSON:
        {
            "order_nodes": [节点ID列表],
            "order_ids": [编号列表],
            "num_couriers": 4,
            "ga_params": {
                "population_size": 200,
                "generations": 500,
                "mutation_rate": 0.2,
                "crossover_rate": 0.8,
                "use_2opt": true,
                "apply_2opt_interval": 10
            }
        }

    对应 daima.py 的步骤3 + 步骤4 + 步骤7
    """
    try:
        data = request.get_json()
        order_nodes = data.get('order_nodes', [])
        order_ids = data.get('order_ids', [])
        num_couriers = data.get('num_couriers', 4)
        ga_params = data.get('ga_params', {})

        node_list = graph_service.get_node_list()
        canteen_id = current_app.config['CANTEEN_NODE_ID']
        canteen_node = node_list[canteen_id - 1]
        positions = graph_service.get_node_positions()

        # ---- 步骤3：构造距离矩阵 ----
        all_locations = [canteen_node] + order_nodes
        location_ids = [canteen_id] + order_ids
        distance_matrix = graph_service.compute_distance_matrix(all_locations)

        # ---- 步骤4：GA + 2-opt 优化 ----
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

        # ---- 步骤7：分配骑手 ----
        courier_assignments = order_service.allocate_couriers(
            optimal_route, all_locations, location_ids,
            num_couriers, canteen_node, canteen_id
        )

        # 构造骑手路线详情
        graph = graph_service.get_graph()
        courier_details = {}

        for cid in range(1, num_couriers + 1):
            loc_indices = courier_assignments[cid]
            if not loc_indices:
                courier_details[cid] = {
                    'orders': [],
                    'distance': 0,
                    'route_coords': []
                }
                continue

            # 该骑手的完整路线：食堂 → 各订单 → 食堂
            courier_locs = [canteen_node] + \
                           [all_locations[idx] for idx in loc_indices] + \
                           [canteen_node]

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

                    # 将路径上每个节点的坐标加入（用于前端画线）
                    for node in path:
                        pos = positions[node]
                        route_coords.append([pos['lat'], pos['lon']])

                except nx.NetworkXNoPath:
                    pass

            courier_details[cid] = {
                'orders': [location_ids[idx] for idx in loc_indices],
                'distance': round(c_distance, 2),
                'route_coords': route_coords
            }

        # 构造最优路线坐标
        optimal_coords = []
        route_node_list = [all_locations[i] for i in optimal_route]
        for node in route_node_list:
            pos = positions[node]
            optimal_coords.append([pos['lat'], pos['lon']])

        return jsonify({
            'success': True,
            'data': {
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
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500