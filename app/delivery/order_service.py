"""
订单管理模块（对应 daima.py 的步骤2和步骤7）

职责：
1. 生成随机订单（对应 daima.py 的 random.sample 部分）
2. 根据 GA 最优路线分配骑手（对应 daima.py 的步骤7）
3. 提供订单的增删查改接口

设计思路：
- 结合数据库持久化（通过 models.py 中的 Order 模型）
- 同时保留内存中的快速操作能力
"""

import random
from flask import current_app
from app.delivery.graph_service import graph_service


class OrderService:
    """订单管理服务"""

    def generate_random_orders(self, num_orders):
        """
        随机生成订单

        对应 daima.py 中的：
            order_nodes = random.sample(node_list, NUM_ORDERS)
            order_ids = [node_list.index(node) + 1 for node in order_nodes]

        参数:
            num_orders: int — 要生成的订单数量

        返回:
            dict: {
                'order_nodes': [真实节点ID列表],
                'order_ids': [1-based 编号列表]
            }
        """
        node_list = graph_service.get_node_list()

        # 检查订单数量是否超过可用节点数
        if num_orders > len(node_list):
            raise ValueError(
                f"订单数量({num_orders})超过可用节点数({len(node_list)})"
            )

        # 无放回随机抽样，保证每个节点最多被选一次
        order_nodes = random.sample(node_list, num_orders)

        # 转换为 1-based 编号（方便算法使用）
        order_ids = [node_list.index(node) + 1 for node in order_nodes]

        return {
            'order_nodes': order_nodes,
            'order_ids': order_ids
        }

    def allocate_couriers(self, optimal_route, all_locations, location_ids,
                          num_couriers, canteen_node, canteen_id):
        """
        根据 GA 最优路线分配骑手

        对应 daima.py 中的 allocate_couriers_by_optimal_route 函数

        策略：按照 GA 的访问顺序，将订单轮转（Round-Robin）分配给各骑手
        例如4个骑手：订单1→骑手1, 订单2→骑手2, 订单3→骑手3, 订单4→骑手4,
                     订单5→骑手1, 订单6→骑手2, ...

        参数:
            optimal_route: GA 输出的最优访问顺序（索引列表）
            all_locations: 所有位置的真实节点列表（[食堂, 订单1, 订单2, ...]）
            location_ids: 对应的编号列表
            num_couriers: 骑手数量
            canteen_node: 食堂的真实节点 ID
            canteen_id: 食堂的编号

        ���回:
            dict: {骑手编号: [该骑手负责的位置索引列表]}
        """
        # 提取所有订单位置（排除食堂）
        order_location_indices = []
        for idx in optimal_route:
            if all_locations[idx] != canteen_node:
                order_location_indices.append(idx)

        # 轮转分配
        courier_assignments = {}
        for courier_id in range(1, num_couriers + 1):
            courier_assignments[courier_id] = []

        for step, location_idx in enumerate(order_location_indices):
            courier_id = (step % num_couriers) + 1
            courier_assignments[courier_id].append(location_idx)

        return courier_assignments


# 全局单例
order_service = OrderService()