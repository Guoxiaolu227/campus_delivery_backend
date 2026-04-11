"""
Flask 应用工厂
★ 本次改动：
  1. db.create_all() → Flask-Migrate
  2. 注册 user/rider/admin 三个新蓝图
"""

from flask import Flask
from config import Config
from app.extensions import db, login_manager, migrate    # ★ 加了 migrate


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )

    app.config.from_object(config_class)

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)    # ★ 新增：绑定迁移工具

    # user_loader（不动）
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # ============================================================
    # 注册蓝图
    # ============================================================

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.delivery import bp as delivery_bp
    app.register_blueprint(delivery_bp, url_prefix='/delivery')

    # ★ 新增：三端蓝图
    from app.user import bp as user_bp
    app.register_blueprint(user_bp, url_prefix='/user')

    from app.rider import bp as rider_bp
    app.register_blueprint(rider_bp, url_prefix='/rider')

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # ★ 删除了 db.create_all()
    # 改用 Flask-Migrate 管理表结构，见下方初始化步骤

    # CLI 命令：初始化 POI（不动）
    @app.cli.command('init-pois')
    def init_pois_command():
        from app.delivery.poi_service import poi_service
        added = poi_service.init_pois()
        print(f"✓ 已初始化 {added} 个 POI")

    # CLI 命令：创建管理员（不动）
    import click

    @app.cli.command('create-admin')
    @click.option('--phone', prompt='管理员手机号', help='手机号')
    @click.option('--username', prompt='用户名', help='用户名')
    @click.option('--password', prompt='密码', hide_input=True, confirmation_prompt=True, help='密码')
    def create_admin_command(phone, username, password):
        from app.models import User
        if User.query.filter_by(phone=phone).first():
            print(f"✗ 手机号 {phone} 已注册")
            return
        admin = User(username=username, phone=phone, role='admin')
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"✓ 管理员 {username}({phone}) 创建成功！")

    return app