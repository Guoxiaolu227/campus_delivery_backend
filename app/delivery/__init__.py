"""
配送业务蓝图初始化
- 这个蓝图包含所有配送相关的 API 接口
- url_prefix='/delivery' 意味着所有路由前面都会加 /delivery
  例如: /delivery/optimize, /delivery/orders 等
"""

from flask import Blueprint

bp = Blueprint('delivery', __name__)

from app.delivery import routes  # noqa: E402, F401