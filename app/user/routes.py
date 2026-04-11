"""
用户端路由

路由一览：
  GET /user/dashboard     — 用户首页（我的订单 + 快速下单）
  POST /user/create_order — 用户下单（调用已有的 order_service）
  GET /user/my_orders     — 我的订单列表（JSON）
"""

from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from app.user import bp
from app.auth.decorators import role_required
from app.delivery.order_service import order_service
from app.delivery.graph_service import graph_service
from app.delivery.poi_service import poi_service


@bp.route('/dashboard')
@login_required
@role_required('user')
def dashboard():
    """用户首页"""
    return render_template('user/dashboard.html')


@bp.route('/create_order', methods=['POST'])
@login_required
@role_required('user')
def create_order():
    """
    用户下单 — 包装已有的 order_service.create_order()
    自动注入 user_id = 当前登录用户
    """
    try:
        data = request.get_json()
        order = order_service.create_order(
            to_poi_id=data.get('to_poi_id'),
            to_node_index=data.get('to_node_index'),
            address=data.get('address', ''),
            user_id=current_user.id    # ★ 自动关联当前用户
        )
        return jsonify({'success': True, 'data': order})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/my_orders')
@login_required
@role_required('user')
def my_orders():
    """获取当前用户的订单（JSON）"""
    from app.models import Order, STATUS_LABELS
    orders = Order.query.filter_by(user_id=current_user.id)\
        .order_by(Order.created_at.desc()).all()
    return jsonify({
        'success': True,
        'data': [o.to_dict() for o in orders]
    })


@bp.route('/pois')
@login_required
@role_required('user')
def get_pois():
    """获取可选配送地点（供下单页下拉框使用）"""
    pois = poi_service.get_all_pois(active_only=True)
    # 排除食堂（食堂是起点，不是目的地）
    destinations = [p for p in pois if p['poi_type'] != 'canteen']
    return jsonify({'success': True, 'data': destinations})