"""
扩展初始化
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate    # ★ 新增

db = SQLAlchemy()
migrate = Migrate()    # ★ 新增：数据库迁移工具实例

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'warning'