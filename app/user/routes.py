"""
用户端路由

路由一览：
  GET  /user/dashboard     — 用户首页
  POST /user/create_order  — 用户下单
  GET  /user/my_orders     — 我的订单列表（JSON）
  POST /user/cancel_order  — 取消订单
  GET  /user/pois          — 可选配送地点
"""

from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from app.user import bp
from app.auth.decorators import role_required
from app.delivery.order_service import order_service
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
    """用户下单"""
    try:
        data = request.get_json()
        order = order_service.create_order(
            to_poi_id=data.get('to_poi_id'),
            to_node_index=data.get('to_node_index'),
            address=data.get('address', ''),
            user_id=current_user.id
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
    """获取当前用户的订单（JSON），附带骑手信息"""
    from app.models import Order, Courier
    orders = Order.query.filter_by(user_id=current_user.id)\
        .order_by(Order.created_at.desc()).all()

    result = []
    for o in orders:
        d = o.to_dict()
        # 附加骑手名称（如果已分配）
        if o.courier_id:
            courier = Courier.query.get(o.courier_id)
            d['courier_name'] = courier.name if courier else f'骑手#{o.courier_id}'
        else:
            d['courier_name'] = ''
        result.append(d)

    return jsonify({'success': True, 'data': result})


@bp.route('/cancel_order', methods=['POST'])
@login_required
@role_required('user')
def cancel_order():
    """取消订单（仅限 pending 状态）"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        order_service.cancel_order(order_id, current_user.id)
        return jsonify({'success': True, 'message': '订单已取消'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pois')
@login_required
@role_required('user')
def get_pois():
    """获取可选配送地点"""
    pois = poi_service.get_all_pois(active_only=True)
    destinations = [p for p in pois if p['poi_type'] != 'canteen']
    return jsonify({'success': True, 'data': destinations})