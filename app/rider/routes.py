"""
骑手端路由

路由一览：
  GET  /rider/dashboard        — 骑手工作台
  GET  /rider/my_deliveries    — 我的配送任务（按路线顺序，JSON）
  POST /rider/update_status    — 推进单个订单状态
  POST /rider/batch_pickup     — 一键取餐（所有 accepted → picked_up）
  POST /rider/start_delivery   — 一键出发（所有 picked_up → delivering）
"""

from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from app.rider import bp
from app.auth.decorators import role_required
from app.delivery.order_service import order_service
from app.extensions import db
from app.models import Order, Courier, STATUS_LABELS, STATUS_TRANSITIONS
from datetime import datetime


@bp.route('/dashboard')
@login_required
@role_required('rider')
def dashboard():
    """骑手工作台"""
    return render_template('rider/dashboard.html')


@bp.route('/my_deliveries')
@login_required
@role_required('rider')
def my_deliveries():
    """
    获取当前骑手的配送任务 — 按 GA 优化路线顺序排列

    返回中会标记：
      - route_index: 配送顺序编号（1, 2, 3, ...）
      - is_current:  是否是当前应该送的那一单
    """
    courier = Courier.query.filter_by(user_id=current_user.id).first()
    if not courier:
        return jsonify({'success': True, 'data': [], 'courier': None})

    # 按路线顺序获取订单
    sorted_orders = order_service.get_rider_route_orders(courier.id)

    # 构建结果，标记当前任务
    result = []
    found_current = False
    for idx, o in enumerate(sorted_orders):
        d = o.to_dict()
        d['route_index'] = idx + 1  # 配送顺序：1, 2, 3, ...

        # "当前任务"是第一个还没送达的 delivering 状态订单
        if not found_current and o.status == 'delivering':
            d['is_current'] = True
            found_current = True
        else:
            d['is_current'] = False

        result.append(d)

    # 统计
    total = len(result)
    delivered = sum(1 for o in sorted_orders if o.status == 'delivered')
    delivering = sum(1 for o in sorted_orders if o.status == 'delivering')
    accepted = sum(1 for o in sorted_orders if o.status == 'accepted')
    picked_up = sum(1 for o in sorted_orders if o.status == 'picked_up')

    return jsonify({
        'success': True,
        'data': result,
        'courier': courier.to_dict(),
        'stats': {
            'total': total,
            'delivered': delivered,
            'delivering': delivering,
            'accepted': accepted,
            'picked_up': picked_up,
        }
    })


@bp.route('/update_status', methods=['POST'])
@login_required
@role_required('rider')
def update_status():
    """骑手推进单个订单状态"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        new_status = data.get('status')

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


@bp.route('/batch_pickup', methods=['POST'])
@login_required
@role_required('rider')
def batch_pickup():
    """
    一键取餐：把当前骑手所有 accepted 订单 → picked_up

    骑手到达食堂后点一次就行，不用一个一个点
    """
    try:
        courier = Courier.query.filter_by(user_id=current_user.id).first()
        if not courier:
            return jsonify({'success': False, 'error': '你不是骑手'}), 403

        orders = Order.query.filter_by(
            courier_id=courier.id, status='accepted'
        ).all()

        now = datetime.utcnow()
        count = 0
        for order in orders:
            order.status = 'picked_up'
            order.picked_up_at = now
            count += 1

        db.session.commit()
        return jsonify({'success': True, 'data': {'updated': count}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/start_delivery', methods=['POST'])
@login_required
@role_required('rider')
def start_delivery():
    """
    一键出发：把当前骑手所有 picked_up 订单 → delivering

    骑手离开食堂时点一次
    """
    try:
        courier = Courier.query.filter_by(user_id=current_user.id).first()
        if not courier:
            return jsonify({'success': False, 'error': '你不是骑手'}), 403

        orders = Order.query.filter_by(
            courier_id=courier.id, status='picked_up'
        ).all()

        now = datetime.utcnow()
        count = 0
        for order in orders:
            order.status = 'delivering'
            order.delivering_at = now
            count += 1

        db.session.commit()
        return jsonify({'success': True, 'data': {'updated': count}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500