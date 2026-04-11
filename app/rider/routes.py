"""
骑手端路由

路由一览：
  GET  /rider/dashboard        — 骑手工作台首页
  GET  /rider/my_deliveries    — 分配给我的配送任务（JSON）
  POST /rider/update_status    — 推进订单状态
"""

from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from app.rider import bp
from app.auth.decorators import role_required
from app.delivery.order_service import order_service
from app.models import Order, Courier, STATUS_LABELS


@bp.route('/dashboard')
@login_required
@role_required('rider')
def dashboard():
    """骑手工作台首页"""
    return render_template('rider/dashboard.html')


@bp.route('/my_deliveries')
@login_required
@role_required('rider')
def my_deliveries():
    """
    获取分配给当前骑手的订单

    查找逻辑：
      1. 通过 current_user.id 找到 Courier 记录
      2. 通过 courier.id 查找关联的 Order
    """
    courier = Courier.query.filter_by(user_id=current_user.id).first()
    if not courier:
        return jsonify({'success': True, 'data': [], 'message': '还没有配送任务'})

    orders = Order.query.filter_by(courier_id=courier.id)\
        .order_by(Order.created_at.desc()).all()

    return jsonify({
        'success': True,
        'data': [o.to_dict() for o in orders],
        'courier': courier.to_dict()
    })


@bp.route('/update_status', methods=['POST'])
@login_required
@role_required('rider')
def update_status():
    """
    骑手推进订单状态

    请求 JSON: {"order_id": 42, "status": "picked_up"}
    """
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        new_status = data.get('status')

        # 安全校验：确认这个订单确实分配给了当前骑手
        courier = Courier.query.filter_by(user_id=current_user.id).first()
        if not courier:
            return jsonify({'success': False, 'error': '你不是骑手'}), 403

        order = Order.query.get(order_id)
        if not order or order.courier_id != courier.id:
            return jsonify({'success': False, 'error': '这个订单不属于你'}), 403

        result = order_service.transition_status(order_id, new_status)
        return jsonify({'success': True, 'data': result})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500