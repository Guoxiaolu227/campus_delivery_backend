"""
数据库模型
★ 用户系统版：新增 User 表，Order/Courier 关联用户

核心变化：
  - User 表：新增，支持三种角色（user/rider/admin）
  - Order 表：新增 user_id 字段（谁下的单）
  - Courier 表：新增 user_id 字段（关联哪个登录账号）
  - Batch / POI / DeliveryResult：完全不动
"""

from datetime import datetime
from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# ================================================================
# ★ 新增：用户表
# ================================================================

class User(UserMixin, db.Model):
    """
    用户表 — 所有人（用户/骑手/管理员）共用一张表

    为什么继承 UserMixin？
      Flask-Login 要求 User 模型必须有 is_authenticated, is_active,
      is_anonymous, get_id() 四个属性/方法。UserMixin 帮你全部实现了，
      你不需要自己写。

    为什么用 role 字段而不是三张表？
      三种角色共享 90% 的字段（手机号、密码、注册时间），
      拆表会导致大量重复代码和频繁 JOIN 查询。
      骑手的额外信息（接单上限、实时位置）放在已有的 Courier 表里通过 user_id 关联。
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), nullable=False, comment='用户名')
    phone = db.Column(db.String(20), unique=True, nullable=False, comment='手机号(唯一)')
    password_hash = db.Column(db.String(256), nullable=False, comment='密码哈希值')
    role = db.Column(db.String(20), nullable=False, default='user',
                     comment='角色: user=普通用户, rider=骑手, admin=管理员')
    is_active = db.Column(db.Boolean, default=True, comment='账号是否启用')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='注册时间')

    # --- 关系 ---
    orders = db.relationship('Order', backref='user', lazy='dynamic')

    def set_password(self, password):
        """
        设置密码（自动哈希，永远不存明文）

        内部调用 werkzeug 的 generate_password_hash()，
        生成类似 'pbkdf2:sha256:260000$...' 的哈希字符串。
        即使数据库泄露，攻击者也无法还原出原始密码。
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """
        验证密码

        把用户输入的明文密码和数据库中的哈希值比对。
        正确返回 True，错误返回 False。
        """
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'phone': self.phone,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


# ================================================================
# 订单状态常量（状态机）— 完全不动
# ================================================================

ORDER_PENDING = 'pending'
ORDER_ACCEPTED = 'accepted'
ORDER_PICKED_UP = 'picked_up'
ORDER_DELIVERING = 'delivering'
ORDER_DELIVERED = 'delivered'

STATUS_TRANSITIONS = {
    ORDER_PENDING:    [ORDER_ACCEPTED],
    ORDER_ACCEPTED:   [ORDER_PICKED_UP],
    ORDER_PICKED_UP:  [ORDER_DELIVERING],
    ORDER_DELIVERING: [ORDER_DELIVERED],
    ORDER_DELIVERED:  []
}

STATUS_LABELS = {
    ORDER_PENDING:    '⏳ 待接单',
    ORDER_ACCEPTED:   '✅ 已接单',
    ORDER_PICKED_UP:  '🍽️ 已取餐',
    ORDER_DELIVERING: '🚴 配送中',
    ORDER_DELIVERED:  '📦 已送达'
}


class Order(db.Model):
    """订单表 — 新增 user_id 字段"""
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # --- ★ 新增：下单用户 ---
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        nullable=True, comment='下单用户ID')

    # --- 位置信息（不动）---
    from_poi_id = db.Column(db.Integer, db.ForeignKey('pois.id'),
                            nullable=True, comment='取餐地点(食堂) POI ID')
    to_poi_id = db.Column(db.Integer, db.ForeignKey('pois.id'),
                          nullable=True, comment='送达地点 POI ID')
    to_node_index = db.Column(db.Integer, nullable=False,
                              comment='目的地路网节点编号(1-based)')
    address = db.Column(db.String(200), default='', comment='目的地描述文字')

    # --- 状态（不动）---
    status = db.Column(db.String(20), default=ORDER_PENDING, comment='订单状态')

    # --- 动态调度（不动）---
    is_frozen = db.Column(db.Boolean, default=False,
                          comment='是否已冻结')
    insert_batch_id = db.Column(db.Integer, nullable=True,
                                comment='动态插入时的原始批次ID')

    # --- 关联（不动）---
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'),
                         nullable=True, comment='所属批次ID')
    courier_id = db.Column(db.Integer, db.ForeignKey('couriers.id'),
                           nullable=True, comment='分配的骑手ID')

    # --- 时间戳（不动）---
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='下单时间')
    accepted_at = db.Column(db.DateTime, nullable=True, comment='接单时间')
    picked_up_at = db.Column(db.DateTime, nullable=True, comment='取餐时间')
    delivering_at = db.Column(db.DateTime, nullable=True, comment='出发配送时间')
    delivered_at = db.Column(db.DateTime, nullable=True, comment='送达时间')

    # --- 关系（不动）---
    from_poi = db.relationship('POI', foreign_keys=[from_poi_id])
    to_poi = db.relationship('POI', foreign_keys=[to_poi_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
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
            'is_frozen': self.is_frozen,
            'is_dynamic': self.insert_batch_id is not None,
        }


class Batch(db.Model):
    """配送批次表 — 完全不动"""
    __tablename__ = 'batches'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_count = db.Column(db.Integer, default=0, comment='订单数')
    courier_count = db.Column(db.Integer, default=0, comment='骑手数')
    total_distance = db.Column(db.Float, default=0.0, comment='最优总距离(米)')
    status = db.Column(db.String(20), default='optimized', comment='批次状态')
    optimal_route_json = db.Column(db.Text, default='', comment='优化结果JSON')
    ga_params_json = db.Column(db.Text, default='', comment='算法参数JSON')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    """骑手表 — 新增 user_id 字段"""
    __tablename__ = 'couriers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False, comment='骑手名称')
    status = db.Column(db.String(20), default='available', comment='骑手状态')

    # ★ 新增：关联登录账号（一个 rider 用户 ↔ 一个骑手记录）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        unique=True, nullable=True, comment='关联用户ID')

    orders = db.relationship('Order', backref='courier', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'user_id': self.user_id,
            'order_count': self.orders.count()
        }


class DeliveryResult(db.Model):
    """配送优化结果表 — 完全不动"""
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


class POI(db.Model):
    """POI 表 — 完全不动"""
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