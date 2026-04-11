"""
主页路由
★ 用户系统版：加 @login_required，未登录自动跳登录页
"""

from flask import render_template
from flask_login import login_required
from app.main import bp


@bp.route('/')
@login_required  # ← ★ 加了这一行：未登录访问 / 会自动跳到 /auth/login
def index():
    """首页路由"""
    return render_template('delivery/index.html')