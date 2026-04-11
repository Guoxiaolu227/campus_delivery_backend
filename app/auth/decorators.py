"""
权限装饰器

用法：
    from app.auth.decorators import role_required

    @bp.route('/admin-only')
    @login_required             # 第一层：必须登录
    @role_required('admin')     # 第二层：必须是管理员
    def admin_page():
        ...

    # 也支持多角色：
    @role_required('admin', 'rider')   # 管理员或骑手都可以访问
"""

from functools import wraps
from flask import abort
from flask_login import current_user


def role_required(*roles):
    """
    角色权限装饰器

    原理：
      1. 检查 current_user 是否已登录（配合 @login_required 使用）
      2. 检查 current_user.role 是否在允许的角色列表中
      3. 不在 → 返回 403 Forbidden

    参数：
      *roles: 允许的角色名，如 'admin', 'rider', 'user'
              可以传多个，满足任意一个即可

    为什么用 *roles（可变参数）而不是单个字符串？
      这样写 @role_required('admin', 'rider') 就能同时允许两种角色，
      比写两个装饰器方便得多。
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # current_user 未登录时是 AnonymousUserMixin，没有 role 属性
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator