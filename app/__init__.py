"""
Flask 应用工厂
★ 用户系统版：初始化 login_manager + 注册 user_loader + 新增 create-admin 命令
"""

from flask import Flask
from config import Config
from app.extensions import db, login_manager  # ← ★ 新增 login_manager


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )

    app.config.from_object(config_class)

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)  # ← ★ 新增：绑定登录管理器

    # ★ 新增：user_loader 回调
    # Flask-Login 通过这个函数，根据 session 中存的 user_id 找到对应的 User 对象
    # 每次请求都会自动调用，返回值就是 current_user
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # 注册蓝图（不动）
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.delivery import bp as delivery_bp
    app.register_blueprint(delivery_bp, url_prefix='/delivery')

    # 创建数据库表（不动）
    with app.app_context():
        db.create_all()

    # CLI 命令：初始化 POI（不动）
    @app.cli.command('init-pois')
    def init_pois_command():
        """命令行初始化 POI：flask init-pois"""
        from app.delivery.poi_service import poi_service
        added = poi_service.init_pois()
        print(f"✓ 已初始化 {added} 个 POI")

    # ★ 新增 CLI 命令：创建管理员账号
    import click

    @app.cli.command('create-admin')
    @click.option('--phone', prompt='管理员手机号', help='手机号')
    @click.option('--username', prompt='用户名', help='用户名')
    @click.option('--password', prompt='密码', hide_input=True, confirmation_prompt=True, help='密码')
    def create_admin_command(phone, username, password):
        """
        命令行创建管理员账号

        用法：flask create-admin
        然后按提示输入手机号、用户名、密码

        或一行搞定：flask create-admin --phone 13800000000 --username admin --password 123456
        """
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