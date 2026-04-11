"""
管理员后台路由
"""

from flask import render_template, jsonify
from flask_login import login_required
from app.admin import bp
from app.auth.decorators import role_required
from app.extensions import db
from app.models import User, Order, Courier, Batch


@bp.route('/dashboard')
@login_required
@role_required('admin')
def dashboard():
    """管理后台首页 — 嵌入原有的完整优化系统"""
    return render_template('admin/dashboard.html')


@bp.route('/api/users')
@login_required
@role_required('admin')
def get_users():
    """获取所有用户列表"""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'success': True, 'data': [u.to_dict() for u in users]})


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