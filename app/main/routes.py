"""
主页路由
- 只有一个首页路由，渲染主页模板
"""

from flask import render_template
from app.main import bp


@bp.route('/')
def index():
    """
    首页路由
    当用户访问 http://localhost:5000/ 时，显示主页
    """
    return render_template('delivery/index.html')