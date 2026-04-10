"""
主页蓝图初始化
- 创建蓝图对象
- 导入路由（必须在蓝图创建之后导入，避免循环引用）
"""

from flask import Blueprint

bp = Blueprint('main', __name__)

from app.main import routes  # noqa: E402, F401