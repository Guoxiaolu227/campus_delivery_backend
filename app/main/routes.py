"""
主页路由 — 登录后根据角色跳转到对应端
"""

from flask import redirect, url_for
from flask_login import login_required, current_user
from app.main import bp


@bp.route('/')
@login_required
def index():
    """
    首页路由 — 角色分流器

    登录后访问 / 会根据角色自动跳转：
      admin → /admin/dashboard
      rider → /rider/dashboard
      user  → /user/dashboard
    """
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif current_user.role == 'rider':
        return redirect(url_for('rider.dashboard'))
    else:
        return redirect(url_for('user.dashboard'))