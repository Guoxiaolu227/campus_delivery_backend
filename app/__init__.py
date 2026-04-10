"""
Flask 应用工厂
- 创建 Flask 实例
- 加载配置
- 初始化扩展（数据库等）
- 注册所有蓝图（模块化路由）
"""

from flask import Flask
from config import Config
from app.extensions import db


def create_app(config_class=Config):
    """
    应用工厂函数

    参数:
        config_class: 配置类，默认使用 Config

    返回:
        配置好的 Flask 应用实例
    """
    # 1. 创建 Flask 实例
    #    template_folder 和 static_folder 指向项目根目录下的文件夹
    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )

    # 2. 从配置类加载所有配置项
    app.config.from_object(config_class)

    # 3. 初始化扩展
    db.init_app(app)

    # 4. 注册蓝图（每个蓝图是一个独立的功能模块）
    #    蓝图的 url_prefix 决定了该模块所有路由的前缀

    # 主页蓝图
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    # 认证蓝图
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # ★ 配送业务蓝图（我们新增的核心模块）
    from app.delivery import bp as delivery_bp
    app.register_blueprint(delivery_bp, url_prefix='/delivery')

    # 5. 在应用上下文中创建数据库表
    with app.app_context():
        db.create_all()

    return app