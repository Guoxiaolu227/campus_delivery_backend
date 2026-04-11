"""
扩展初始化
- 在这里创建扩展实例（但不绑定 app）
- 实际绑定在 create_app() 中通过 .init_app(app) 完成
- 这样做可以避免循环导入的问题
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# 创建数据库实例（此时还没有绑定任何 Flask 应用）
db = SQLAlchemy()

# ★ 新增：创建登录管理器实例
login_manager = LoginManager()
login_manager.login_view = 'auth.login'          # 未登录时跳转到哪个路由
login_manager.login_message = '请先登录'           # 跳转时的提示信息
login_manager.login_message_category = 'warning'  # 提示信息的类别
