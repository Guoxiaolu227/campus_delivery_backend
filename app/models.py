"""
数据库模型
★ 阶段2重写：订单系统化

核心变化：
  - Order 表：新增完整状态机（5种状态 + 5个时间戳）
  - Batch 表：新增配送批次，每次优化 = 一个批次
  - Courier 表：保留，小幅调整
  - POI 表：不变
"""

from datetime import datetime
from app.extensions import db


# ================================================================
# 订单状态常量（状态机）
# ================================================================
# 为什么用常量而不是硬编码字符串？
# 1. 防拼写错误：写错 "pendng" 不会报错，但 ORDER_PENDING 未定义会立刻报错
# 2. 方便全局搜索：Ctrl+F 搜 ORDER_PENDING 能找到所有使用的地方
# 3. 后续可以加中文描述映射

ORDER_PENDING = 'pending'         # 待接单：用户刚下的单，还没被纳入任何批次
ORDER_ACCEPTED = 'accepted'       # 已接单：已被纳入某个批次，分配了骑手
ORDER_PICKED_UP = 'picked_up'     # 已取餐：骑手到达食堂取了餐
ORDER_DELIVERING = 'delivering'   # 配送中：骑手出发配送
ORDER_DELIVERED = 'delivered'     # 已送达：骑手到达目的地

# 状态流转规则：当前状态 → 允许转到的下一状态
STATUS_TRANSITIONS = {
    ORDER_PENDING:    [ORDER_ACCEPTED],
    ORDER_ACCEPTED:   [ORDER_PICKED_UP],
    ORDER_PICKED_UP:  [ORDER_DELIVERING],
    ORDER_DELIVERING: [ORDER_DELIVERED],
    ORDER_DELIVERED:  []  # 终态，不能再转
}

# 状态中文映射（前端展示用）
STATUS_LABELS = {
    ORDER_PENDING:    '⏳ 待接单',
    ORDER_ACCEPTED:   '✅ 已接单',
    ORDER_PICKED_UP:  '🍽️ 已取餐',
    ORDER_DELIVERING: '🚴 配送中',
    ORDER_DELIVERED:  '📦 已送达'
}


class Order(db.Model):
    """
    订单表（★ 阶段2重写）

    每条记录 = 一个外卖订单

    与旧版的区别：
      旧版：只有 node_id + status，从未被真正使用
      新版：
        - 关联 POI（from_poi_id=食堂, to_poi_id=目的地）
        - 完整状态机（5种状态 + 5个时间戳）
        - 归属批次（batch_id，哪一批优化处理的）
        - 归属骑手（courier_id，分配给谁）

    关于 node_index：
      直接存目的地的路网节点编号（1-based），这样优化算法可以直接使用，
      不需要每次都去 POI 表查。
    """
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # --- 位置信息 ---
    from_poi_id = db.Column(db.Integer, db.ForeignKey('pois.id'),
                            nullable=True, comment='取餐地点(食堂) POI ID')
    to_poi_id = db.Column(db.Integer, db.ForeignKey('pois.id'),
                          nullable=True, comment='送达地点 POI ID')
    to_node_index = db.Column(db.Integer, nullable=False,
                              comment='目的地路网节点编号(1-based)')
    address = db.Column(db.String(200), default='', comment='目的地描述文字')

    # --- 状态 ---
    status = db.Column(db.String(20), default=ORDER_PENDING, comment='订单状态')

    # --- ★ 阶段4新增：动态调度相关 ---
    is_frozen = db.Column(db.Boolean, default=False,
                          comment='是否已冻结（骑手已经过该点，不可调整）')
    insert_batch_id = db.Column(db.Integer, nullable=True,
                                comment='动态插入时的原始批次ID（区分初始订单和动态插入的）')
    # --- 关联 ---
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'),
                         nullable=True, comment='所属批次ID')
    courier_id = db.Column(db.Integer, db.ForeignKey('couriers.id'),
                           nullable=True, comment='分配的骑手ID')

    # --- 时间戳（每个状态变化记录时间，用于统计配送耗时）---
    created_at = db.Column(db.DateTime, default=datetime.utcnow,
                           comment='下单时间')
    accepted_at = db.Column(db.DateTime, nullable=True,
                            comment='接单时间')
    picked_up_at = db.Column(db.DateTime, nullable=True,
                             comment='取餐时间')
    delivering_at = db.Column(db.DateTime, nullable=True,
                              comment='出发配送时间')
    delivered_at = db.Column(db.DateTime, nullable=True,
                             comment='送达时间')

    # --- 关系（方便反向查询）---
    from_poi = db.relationship('POI', foreign_keys=[from_poi_id])
    to_poi = db.relationship('POI', foreign_keys=[to_poi_id])

    def to_dict(self):
        """转为字典，方便 JSON 返回前端"""
        return {
            'id': self.id,
            'from_poi_id': self.from_poi_id,
            'from_poi_name': self.from_poi.name if self.from_poi else '嘉慧园食堂',
            'to_poi_id': self.to_poi_id,
            'to_poi_name': self.to_poi.name if self.to_poi else '',
            'to_node_index': self.to_node_index,
            'address': self.address,
            'status': self.status,
            'status_label': STATUS_LABELS.get(self.status, self.status),
            'batch_id': self.batch_id,
            'courier_id': self.courier_id,
            'created_at': self.created_at.strftime('%H:%M:%S') if self.created_at else '',
            'accepted_at': self.accepted_at.strftime('%H:%M:%S') if self.accepted_at else '',
            'delivered_at': self.delivered_at.strftime('%H:%M:%S') if self.delivered_at else '',
            # 在 to_dict() 的 return 字典里，'delivered_at' 那行后面加：
            'is_frozen': self.is_frozen,
            'is_dynamic': self.insert_batch_id is not None,  # 是否为动态插入的订单
        }


class Batch(db.Model):
    """
    配送批次表（★ 阶段2新增）

    作用：
      每次点击"开始优化"时，把当前所有 pending 订单打包成一个批次。
      一个批次 = 一次 GA 优化运算 = 一组骑手路线方案。

    为什么需要批次？
      1. 历史可追溯：第1批10单、第2批8单，各自的路线方案互不干扰
      2. 为动态调度奠定基础：新订单进入下一个批次
      3. 支持"再次优化"：同一批次可以用不同参数重新计算

    字段说明：
      - order_count: 这批有多少单
      - total_distance: GA 优化后的最优总距离
      - courier_count: 参与配送的骑手数
      - optimal_route_json: 完整优化结果（JSON），包含路线和骑手分配
      - ga_params_json: 本次使用的 GA 参数快照
    """
    __tablename__ = 'batches'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_count = db.Column(db.Integer, default=0, comment='订单数')
    courier_count = db.Column(db.Integer, default=0, comment='骑手数')
    total_distance = db.Column(db.Float, default=0.0, comment='最优总距离(米)')
    status = db.Column(db.String(20), default='optimized', comment='批次状态')
    optimal_route_json = db.Column(db.Text, default='', comment='优化结果JSON')
    ga_params_json = db.Column(db.Text, default='', comment='算法参数JSON')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关联的订单
    orders = db.relationship('Order', backref='batch', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'order_count': self.order_count,
            'courier_count': self.courier_count,
            'total_distance': self.total_distance,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }


class Courier(db.Model):
    """骑手表（保留，小幅调整）"""
    __tablename__ = 'couriers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False, comment='骑手名称')
    status = db.Column(db.String(20), default='available', comment='骑手状态')
    orders = db.relationship('Order', backref='courier', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'order_count': self.orders.count()
        }


class DeliveryResult(db.Model):
    """配送优化结果表（保留，后续可和 Batch 关联）"""
    __tablename__ = 'delivery_results'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    total_distance = db.Column(db.Float, comment='最优总距离')
    optimal_route = db.Column(db.Text, comment='最优路线JSON')
    courier_assignments = db.Column(db.Text, comment='骑手分配方案JSON')
    ga_params = db.Column(db.Text, comment='算法参数JSON')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'total_distance': self.total_distance,
            'optimal_route': self.optimal_route,
            'courier_assignments': self.courier_assignments,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }


# ================================================================
# POI 表（阶段1已有，完全不改）
# ================================================================

class POI(db.Model):
    __tablename__ = 'pois'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, comment='地点名称')
    poi_type = db.Column(db.String(20), nullable=False, comment='地点类型')
    node_index = db.Column(db.Integer, nullable=False, comment='路网节点编号(1-based)')
    lat = db.Column(db.Float, nullable=False, default=0.0, comment='纬度')
    lon = db.Column(db.Float, nullable=False, default=0.0, comment='经度')
    description = db.Column(db.String(200), default='', comment='描述')
    capacity = db.Column(db.Integer, default=0, comment='容量')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'poi_type': self.poi_type,
            'node_index': self.node_index,
            'lat': self.lat,
            'lon': self.lon,
            'description': self.description,
            'capacity': self.capacity,
            'is_active': self.is_active
        }