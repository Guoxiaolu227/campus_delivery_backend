"""
Flask 应用工厂
"""

from flask import Flask
from config import Config
from app.extensions import db


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )

    app.config.from_object(config_class)
    db.init_app(app)

    # 注册蓝图
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.delivery import bp as delivery_bp
    app.register_blueprint(delivery_bp, url_prefix='/delivery')

    # 创建数据库表
    with app.app_context():
        db.create_all()

    # ★ 阶段1新增：注册 CLI 命令
    @app.cli.command('init-pois')
    def init_pois_command():
        """命令行初始化 POI：flask init-pois"""
        from app.delivery.poi_service import poi_service
        added = poi_service.init_pois()
        print(f"✓ 已初始化 {added} 个 POI")

    return app