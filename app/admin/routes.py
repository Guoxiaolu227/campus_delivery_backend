"""
管理员后台路由

路由一览：
  GET  /admin/dashboard    — 管理后台首页（嵌入现有的优化系统页面）
  GET  /admin/users        — 用户管理页面
  GET  /admin/api/users    — 用户列表 API（JSON）
  POST /admin/api/users/<id>/toggle  — 启用/禁用用户
"""

from flask import render_template, jsonify, request
from flask_login import login_required
from app.admin import bp
from app.auth.decorators import role_required
from app.extensions import db
from app.models import User, Order, Courier


@bp.route('/dashboard')
@login_required
@role_required('admin')
def dashboard():
    """
    管理后台首页

    直接渲染原有的 delivery/index.html（你已经做好的优化系统界面）。
    这样管理员的所有原有功能（加载路网、下单、优化、调度）全部保留，零修改。
    """
    return render_template('admin/dashboard.html')


@bp.route('/api/users')
@login_required
@role_required('admin')
def get_users():
    """获取所有用户列表"""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({
        'success': True,
        'data': [u.to_dict() for u in users]
    })


@bp.route('/api/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@role_required('admin')
def toggle_user(user_id):
    """启用/禁用用户"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    if user.role == 'admin':
        return jsonify({'success': False, 'error': '不能禁用管理员'}), 400

    user.is_active = not user.is_active
    db.session.commit()
    action = '启用' if user.is_active else '禁用'
    return jsonify({'success': True, 'message': f'已{action} {user.username}'})


@bp.route('/api/stats')
@login_required
@role_required('admin')
def get_stats():
    """管理员数据概览"""
    from app.models import Batch
    return jsonify({
        'success': True,
        'data': {
            'total_users': User.query.count(),
            'total_riders': User.query.filter_by(role='rider').count(),
            'total_orders': Order.query.count(),
            'pending_orders': Order.query.filter_by(status='pending').count(),
            'delivering_orders': Order.query.filter_by(status='delivering').count(),
            'delivered_orders': Order.query.filter_by(status='delivered').count(),
            'total_batches': Batch.query.count(),
        }
    })