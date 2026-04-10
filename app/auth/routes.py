from flask import jsonify
from app.auth import bp


@bp.route('/login')
def login():
    """登录页面（占位，后续实现）"""
    return jsonify({'message': '登录功能开发中'})