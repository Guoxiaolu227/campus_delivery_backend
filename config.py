"""
配置文件
- 存放数据库连接字符串、密钥、调试开关等
- 不同环境（开发/生产）可以用不同的配置类
"""

import os

# 获取项目根目录的绝对路径，用于拼接数据库文件路径
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """基础配置类"""

    # Flask 密钥，用于 session 加密（生产环境请改为随机字符串）
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'campus-delivery-secret-key-2024'

    # SQLite 数据库路径，数据文件会保存在项目根目录下
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'delivery.db')

    # 关闭 SQLAlchemy 的事件通知系统（节省内存）
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ===== 校园配送专属配置 =====
    SCHOOL_CENTER_LAT = 30.57978       # 武汉理工大学中心纬度
    SCHOOL_CENTER_LON = 114.32819      # 武汉理工大学中心经度
    SCHOOL_NAME = "Wuhan University of Technology"
    CAMPUS_RADIUS = 400                # 校园覆盖半径（米）
    CANTEEN_NODE_ID = 10               # 食堂节点编号（从1开始）