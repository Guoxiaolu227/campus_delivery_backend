"""
地图建模模块（对应 daima.py 的步骤1和步骤3）

职责：
1. 从 OpenStreetMap 获取校园路网数据
2. 提取节点列表和坐标信息
3. 计算任意两点之间的最短路径距离矩阵

设计思路：
- 使用单例模式：路网数据只���载一次，后续请求直接复用
- 封装为类：方便管理状态和被其他模块调用
"""

import osmnx as ox
import networkx as nx
import numpy as np
from flask import current_app


class GraphService:
    """校园路网服务（单例缓存）"""

    def __init__(self):
        # 缓存：路网图只加载一次
        self._graph = None
        # 缓存：节点列表
        self._node_list = None
        # 缓存：节点坐标字典 {node_id: (经度, 纬度)}
        self._node_positions = None

    def get_graph(self):
        """
        获取校园路网图（带缓存）

        对应 daima.py 中的：
            campus_graph = ox.graph_from_point(...)

        返回:
            networkx.MultiDiGraph: OSMnx 路网图对象
        """
        if self._graph is None:
            # 从 Flask 配置中读取学校坐标和半径
            lat = current_app.config['SCHOOL_CENTER_LAT']
            lon = current_app.config['SCHOOL_CENTER_LON']
            radius = current_app.config['CAMPUS_RADIUS']

            print(f"🔄 正在从 OpenStreetMap 获取路网数据...")
            print(f"   中心: ({lat}, {lon}), 半径: {radius}米")

            # 调用 osmnx 下载路网（步行网络）
            self._graph = ox.graph_from_point(
                center_point=(lat, lon),
                dist=radius,
                network_type='walk'  # 步行网络，适合校园内配送
            )

            print(f"✓ 路网加载成功！节点: {len(self._graph.nodes())}，边: {len(self._graph.edges())}")

        return self._graph

    def get_node_list(self):
        """
        获取所有节点的列表

        对应 daima.py 中的：
            node_list = list(campus_graph.nodes())

        返回:
            list: 节点 ID 列表
        """
        if self._node_list is None:
            graph = self.get_graph()
            self._node_list = list(graph.nodes())
        return self._node_list

    def get_node_positions(self):
        """
        获取所有节点的坐标

        对应 daima.py 中的：
            node_positions = {node: (data['x'], data['y']) for ...}

        返回:
            dict: {节点ID: {'lat': 纬度, 'lon': 经度}}
        """
        if self._node_positions is None:
            graph = self.get_graph()
            self._node_positions = {}
            for node, data in graph.nodes(data=True):
                self._node_positions[node] = {
                    'lat': data['y'],   # y 是纬度
                    'lon': data['x']    # x 是经度
                }
        return self._node_positions

    def compute_distance_matrix(self, location_nodes):
        """
        计算给定节点列表之间的最短距离矩阵

        对应 daima.py 中的步骤3（整个距离矩阵计算循环）

        参数:
            location_nodes: list[int] — 节点 ID 列表
                            第0个元素通常是食堂（起点）

        返回:
            numpy.ndarray: n×n 的距离矩阵（单位：米）
        """
        graph = self.get_graph()
        n = len(location_nodes)
        matrix = np.zeros((n, n))

        print(f"🔍 计算距离矩阵 ({n}×{n})...")

        for i in range(n):
            for j in range(i + 1, n):
                try:
                    # 用 Dijkstra 算法求最短路径
                    path = nx.shortest_path(
                        graph,
                        location_nodes[i],
                        location_nodes[j],
                        weight='length'
                    )
                    # 累加路径上每条边的长度
                    distance = sum(
                        graph[path[k]][path[k + 1]][0]['length']
                        for k in range(len(path) - 1)
                    )
                    matrix[i][j] = distance
                    matrix[j][i] = distance
                except nx.NetworkXNoPath:
                    # 两点之间没有路径，设为无穷大
                    matrix[i][j] = float('inf')
                    matrix[j][i] = float('inf')

        print(f"✓ 距离矩阵计算完成！")
        return matrix

    def get_shortest_path(self, from_node, to_node):
        """
        获取两点之间的最短路径（用于前端绘制路线）

        返回:
            list[dict]: 路径上每个节点的坐标 [{'lat': ..., 'lon': ...}, ...]
        """
        graph = self.get_graph()
        positions = self.get_node_positions()

        try:
            path = nx.shortest_path(graph, from_node, to_node, weight='length')
            return [positions[node] for node in path]
        except nx.NetworkXNoPath:
            return []

    def find_nearest_node_info(self, lat, lon):
        """
        ★ 阶段1新增：根据经纬度查找最近的路网节点

        用途：用户在地图上点击时，返回最近节点的编号和坐标
        """
        import math

        node_list = self.get_node_list()
        positions = self.get_node_positions()

        min_d = float('inf')
        result = None

        for i, node in enumerate(node_list):
            pos = positions[node]
            R = 6371000
            p1, p2 = math.radians(lat), math.radians(pos['lat'])
            dp = math.radians(pos['lat'] - lat)
            dl = math.radians(pos['lon'] - lon)
            a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
            d = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

            if d < min_d:
                min_d = d
                result = {
                    'node_id': int(node),
                    'node_index': i + 1,
                    'lat': pos['lat'],
                    'lon': pos['lon'],
                    'distance': round(d, 2)
                }

        return result


# ★ 创建全局单例实例，其他模块直接导入使用
graph_service = GraphService()
