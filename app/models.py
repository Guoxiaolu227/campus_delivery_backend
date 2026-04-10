# Models go here
"""
数据库模型
- 定义所有数据表的结构
- Order: 订单表（核心）
- Courier: 骑手表
- DeliveryResult: 优化结果表
"""

from datetime import datetime
from app.extensions import db


class Order(db.Model):
    """
    订单表
    每条记录代表一个外卖订单
    """
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # 订单对应的路网节点编号（1-based，对应 node_list 中的位置）
    node_id = db.Column(db.Integer, nullable=False, comment='路网节点编号')

    # 配送地址的文字描述（方便前端展示）
    address = db.Column(db.String(200), default='', comment='配送地址描述')

    # 订单状态：pending=待配送, assigned=已分配, delivered=已送达
    status = db.Column(db.String(20), default='pending', comment='订单状态')

    # 分配给哪个骑手（外键关联 couriers 表）
    courier_id = db.Column(db.Integer, db.ForeignKey('couriers.id'),
                           nullable=True, comment='分配的骑手ID')

    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """转换为字典，方便 JSON 序列化返回给前端"""
        return {
            'id': self.id,
            'node_id': self.node_id,
            'address': self.address,
            'status': self.status,
            'courier_id': self.courier_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }


class Courier(db.Model):
    """
    骑手表
    每条记录代表一个配送骑手
    """
    __tablename__ = 'couriers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # 骑手名称
    name = db.Column(db.String(50), nullable=False, comment='骑手名称')

    # 骑手状态：available=空闲, busy=配送中
    status = db.Column(db.String(20), default='available', comment='骑手状态')

    # 关联的订单（一个骑手可以有多个订单）
    orders = db.relationship('Order', backref='courier', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'order_count': self.orders.count()
        }


class DeliveryResult(db.Model):
    """
    配送优化结果表
    每次运行 GA 优化后，把结果保存在这里
    """
    __tablename__ = 'delivery_results'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # 最优总距离（米）
    total_distance = db.Column(db.Float, comment='最优总距离')

    # 最优路线顺序（JSON 字符串存储）
    optimal_route = db.Column(db.Text, comment='最优路线JSON')

    # 骑手分配方案（JSON 字符串存储）
    courier_assignments = db.Column(db.Text, comment='骑手分配方案JSON')

    # GA 算法参数快照
    ga_params = db.Column(db.Text, comment='算法参数JSON')

    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'total_distance': self.total_distance,
            'optimal_route': self.optimal_route,
            'courier_assignments': self.courier_assignments,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }