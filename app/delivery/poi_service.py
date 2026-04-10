"""
POI 管理服务（★ 阶段1新增）

职责：
  1. 初始化：首次启动时把 config.py 中预设的校园地点写���数据库
  2. 增删改查：管理校园地点
  3. 坐标匹配：用户在地图上点击 → 自动找到最近的路网节点
"""

import math
from flask import current_app
from app.extensions import db
from app.models import POI
from app.delivery.graph_service import graph_service


# POI 类型白名单，添加地点时会校验
VALID_POI_TYPES = ['canteen', 'dormitory', 'teaching', 'library', 'sports', 'other']


class POIService:
    """POI 管理服务"""

    def init_pois(self):
        """
        初始化 POI 数据 —— 把 config.py 中 CAMPUS_POIS 的预设地点写入数据库

        逻辑：
          遍历预设列表，按名称判重 → 不存在的才插入 → 自动从路网获取坐标

        调用时机：
          用户在前端点击「初始化地点」按钮，或命令行执行 flask init-pois
        """
        pois_config = current_app.config.get('CAMPUS_POIS', [])
        if not pois_config:
            return 0

        # 尝试获取路网坐标
        try:
            node_list = graph_service.get_node_list()
            positions = graph_service.get_node_positions()
            graph_ok = True
        except Exception:
            graph_ok = False

        added = 0
        for item in pois_config:
            # 按名称去重
            if POI.query.filter_by(name=item['name']).first():
                continue

            idx = item['node_index']
            lat, lon = 0.0, 0.0

            # 从路网查坐标
            if graph_ok and 1 <= idx <= len(node_list):
                real_node = node_list[idx - 1]
                pos = positions.get(real_node, {})
                lat = pos.get('lat', 0.0)
                lon = pos.get('lon', 0.0)

            poi = POI(
                name=item['name'],
                poi_type=item['poi_type'],
                node_index=idx,
                lat=lat,
                lon=lon,
                description=item.get('description', ''),
                capacity=item.get('capacity', 0),
                is_active=True
            )
            db.session.add(poi)
            added += 1

        if added > 0:
            db.session.commit()
        return added

    # ------ 查询 ------

    def get_all_pois(self, poi_type=None, active_only=True):
        """
        获取 POI 列表

        参数:
          poi_type:    筛选类型，None=全部
          active_only: True=只返回启用的
        """
        query = POI.query
        if active_only:
            query = query.filter_by(is_active=True)
        if poi_type:
            query = query.filter_by(poi_type=poi_type)
        return [p.to_dict() for p in query.order_by(POI.poi_type, POI.name).all()]

    def get_canteen(self):
        """
        获取唯一的食堂/配送中心

        简化设定：系统中只有1个食堂（嘉慧园，19号节点）
        """
        poi = POI.query.filter_by(poi_type='canteen', is_active=True).first()
        return poi.to_dict() if poi else None

    # ------ 创建 ------

    def create_poi(self, name, poi_type, node_index=None, lat=None, lon=None,
                   description='', capacity=0):
        """
        创建新 POI

        两种定位方式：
          方式1：给 node_index → 自动查坐标
          方式2：给 lat+lon   → 自动匹配最近节点

        业务规则：
          - canteen 类型最多只能有1个（嘉慧园食堂固定不变）
          - 名称不能重复
        """
        if poi_type not in VALID_POI_TYPES:
            raise ValueError(f"无效类型: {poi_type}，可选: {VALID_POI_TYPES}")

        if poi_type == 'canteen':
            existing = POI.query.filter_by(poi_type='canteen', is_active=True).first()
            if existing:
                raise ValueError(f"食堂已存在: {existing.name}（系统仅支持1个食堂）")

        if POI.query.filter_by(name=name).first():
            raise ValueError(f"名称 '{name}' 已存在")

        node_list = graph_service.get_node_list()
        positions = graph_service.get_node_positions()

        if node_index is not None:
            if node_index < 1 or node_index > len(node_list):
                raise ValueError(f"node_index={node_index} 超出范围 [1, {len(node_list)}]")
            real_node = node_list[node_index - 1]
            pos = positions[real_node]
            lat, lon = pos['lat'], pos['lon']
        elif lat is not None and lon is not None:
            node_index = self._find_nearest_node_index(lat, lon, node_list, positions)
            real_node = node_list[node_index - 1]
            pos = positions[real_node]
            lat, lon = pos['lat'], pos['lon']
        else:
            raise ValueError("必须提供 node_index 或 lat+lon")

        poi = POI(
            name=name, poi_type=poi_type, node_index=node_index,
            lat=lat, lon=lon, description=description,
            capacity=capacity, is_active=True
        )
        db.session.add(poi)
        db.session.commit()
        return poi.to_dict()

    # ------ 更新 ------

    def update_poi(self, poi_id, **kwargs):
        """更新 POI 字段（只更新传入的字段）"""
        poi = POI.query.get(poi_id)
        if not poi:
            raise ValueError(f"POI ID={poi_id} 不存在")

        # 禁止修改食堂类型
        if poi.poi_type == 'canteen' and kwargs.get('poi_type', 'canteen') != 'canteen':
            raise ValueError("不能更改食堂的类型")

        node_list = graph_service.get_node_list()
        positions = graph_service.get_node_positions()

        # 如果更新了 node_index，自动刷新坐标
        if 'node_index' in kwargs:
            idx = kwargs['node_index']
            if 1 <= idx <= len(node_list):
                real_node = node_list[idx - 1]
                pos = positions[real_node]
                kwargs['lat'] = pos['lat']
                kwargs['lon'] = pos['lon']

        allowed = ['name', 'poi_type', 'node_index', 'lat', 'lon',
                   'description', 'capacity', 'is_active']
        for field in allowed:
            if field in kwargs:
                setattr(poi, field, kwargs[field])

        db.session.commit()
        return poi.to_dict()

    # ------ 删除 ------

    def delete_poi(self, poi_id):
        """软删除 POI（设置 is_active=False）"""
        poi = POI.query.get(poi_id)
        if not poi:
            raise ValueError(f"POI ID={poi_id} 不存在")
        if poi.poi_type == 'canteen':
            raise ValueError("食堂/配送中心不能删除")
        poi.is_active = False
        db.session.commit()
        return {'message': f'已禁用: {poi.name}'}

    # ------ 坐标刷新 ------

    def refresh_coordinates(self):
        """刷新所有 POI 坐标（路网重新加载后调用）"""
        node_list = graph_service.get_node_list()
        positions = graph_service.get_node_positions()
        updated = 0
        for poi in POI.query.all():
            if 1 <= poi.node_index <= len(node_list):
                real_node = node_list[poi.node_index - 1]
                pos = positions[real_node]
                if poi.lat != pos['lat'] or poi.lon != pos['lon']:
                    poi.lat = pos['lat']
                    poi.lon = pos['lon']
                    updated += 1
        if updated:
            db.session.commit()
        return updated

    # ------ 内部工具方法 ------

    @staticmethod
    def _find_nearest_node_index(lat, lon, node_list, positions):
        """找到距离 (lat, lon) 最近的路网节点，返回 1-based 编号"""
        min_d = float('inf')
        best = 1
        for i, node in enumerate(node_list):
            pos = positions[node]
            d = POIService._haversine(lat, lon, pos['lat'], pos['lon'])
            if d < min_d:
                min_d = d
                best = i + 1
        return best

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        """Haversine 公式：计算两个经纬度之间的距离（米）"""
        R = 6371000
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# 全局单例
poi_service = POIService()