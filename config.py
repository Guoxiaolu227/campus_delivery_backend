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
    SCHOOL_CENTER_LAT = 30.57978       # 湖北大学中心纬度
    SCHOOL_CENTER_LON = 114.32819      # 湖北大学中心经度
    SCHOOL_NAME = "Hubei University"
    CAMPUS_RADIUS = 400                # 校园覆盖半径（米）
    CANTEEN_NODE_ID = 19               # ★ 嘉慧园食堂节点编号（从1开始）

    # # ===== 校园配送专属配置 =====
    # SCHOOL_CENTER_LAT = 32.030326131572934       # 南京理工大学中心纬度
    # SCHOOL_CENTER_LON = 118.85484430503536      # 南京理工大学中心经度
    # SCHOOL_NAME = "Nanjing University of Science and Technology"
    # CAMPUS_RADIUS = 600                # 校园覆盖半径（米）
    # CANTEEN_NODE_ID = 19               # ★ 食堂节点编号（从1开始）

    # ===== ★ 阶段1新增：校园 POI 预设数据 =====
    # 说明：
    #   - node_index 是路网节点编号（1-based），启动后可通过地图点击确认
    #   - poi_type 类型说明：
    #       canteen   = 食堂/配送中心（固定1个，即嘉慧园）
    #       dormitory = 宿舍楼
    #       teaching  = 教学楼/学院
    #       library   = 图书馆
    #       sports    = 体育场馆
    #       other     = 其他可配送地点
    #   - 你可以随时通过前端"添加地点"功能补充更多
    #   - node_index 的值需要根据实际路网调整（启动后在地图上点击查看）
    CAMPUS_POIS = [
        # ===== 食堂 & 配送中心（固定1个）=====
        {
            'name': '嘉慧园食堂',
            'poi_type': 'canteen',
            'node_index': 19,
            'description': '食堂 & 配送中心（所有订单的起点）',
            'capacity': 500
        },
        # ===== 宿舍楼 =====
        {
            'name': '东苑1栋宿舍',
            'poi_type': 'dormitory',
            'node_index': 5,
            'description': '东区学生宿舍',
            'capacity': 400
        },
        {
            'name': '东苑2栋宿舍',
            'poi_type': 'dormitory',
            'node_index': 8,
            'description': '东区学生宿舍',
            'capacity': 400
        },
        {
            'name': '西苑1栋宿舍',
            'poi_type': 'dormitory',
            'node_index': 25,
            'description': '西区学生宿舍',
            'capacity': 350
        },
        {
            'name': '南苑1栋宿舍',
            'poi_type': 'dormitory',
            'node_index': 35,
            'description': '南区学生宿舍',
            'capacity': 300
        },
        # ===== 教学楼 / 学院 =====
        {
            'name': '理学院楼',
            'poi_type': 'teaching',
            'node_index': 12,
            'description': '理学院教学楼',
            'capacity': 0
        },
        {
            'name': '计算机学院楼',
            'poi_type': 'teaching',
            'node_index': 30,
            'description': '计算机科学与技术学院',
            'capacity': 0
        },
        # ===== 图书馆 =====
        {
            'name': '图书馆',
            'poi_type': 'library',
            'node_index': 15,
            'description': '校图书馆',
            'capacity': 0
        },
        # ===== 体育场馆 =====
        {
            'name': '体育馆',
            'poi_type': 'sports',
            'node_index': 40,
            'description': '校体育馆',
            'capacity': 0
        },
    ]
    # ===== ★ 阶段4新增：动态调度配置 =====
    SCHEDULER_REOPTIMIZE_INTERVAL = 60    # 后台全局微调间隔（秒）
    SCHEDULER_AUTO_START = True           # 批次优化后是否自动启动后台线程
