"""
认证路由：注册 / 登录 / 退出

路由一览：
  GET  /auth/login     — 显示登录页面
  POST /auth/login     — 处理登录表单
  GET  /auth/register  — 显示注册页面
  POST /auth/register  — 处理注册表单
  GET  /auth/logout    — 退出登录
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import bp
from app.extensions import db
from app.models import User, Courier


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    登录

    GET  → 显示登录页面
    POST → 接收表单 → 验证手机号+密码 → 登录成功跳转
    """
    # 如果已经登录了，直接跳到首页
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        # ---------- 校验 ----------
        if not phone or not password:
            flash('请填写手机号和密码', 'danger')
            return render_template('auth/login.html')

        user = User.query.filter_by(phone=phone).first()

        if user is None:
            flash('该手机号未注册', 'danger')
            return render_template('auth/login.html')

        if not user.check_password(password):
            flash('密码错误', 'danger')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('账号已被禁用，请联系管理员', 'danger')
            return render_template('auth/login.html')

        # ---------- 登录成功 ----------
        login_user(user, remember=True)
        # remember=True：关闭浏览器后下次打开仍然保持登录

        flash(f'欢迎回来，{user.username}！', 'success')

        # 跳转到登录前想访问的页面（如果有的话），否则按角色跳转
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        # ★ 按角色跳转到对应端
        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'rider':
            return redirect(url_for('rider.dashboard'))
        else:
            return redirect(url_for('user.dashboard'))

    # GET 请求：显示登录页面
    return render_template('auth/login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    注册

    GET  → 显示注册页面
    POST → 接收表单 → 校验 → 创建用户 → 自动登录 → 跳转
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        role = request.form.get('role', 'user')

        # ---------- 校验 ----------
        errors = []
        if not username:
            errors.append('请填写用户名')
        if not phone:
            errors.append('请填写手机号')
        if len(phone) != 11 or not phone.isdigit():
            errors.append('手机号必须是11位数字')
        if not password or len(password) < 6:
            errors.append('密码至少6位')
        if password != password2:
            errors.append('两次密码不一致')
        if role not in ('user', 'rider'):
            errors.append('角色只能选 用户 或 骑手')
        if User.query.filter_by(phone=phone).first():
            errors.append('该手机号已注册')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html')

        # ---------- 创建用户 ----------
        user = User(username=username, phone=phone, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # 获取 user.id

        # 如果注册的是骑手，自动在 Courier 表创建一条记录
        if role == 'rider':
            courier = Courier(name=username, status='available', user_id=user.id)
            db.session.add(courier)

        db.session.commit()

        # ---------- 自动登录 ----------
        login_user(user, remember=True)
        flash(f'注册成功！欢迎 {username}', 'success')
        # ★ 按角色跳转
        if user.role == 'rider':
            return redirect(url_for('rider.dashboard'))
        else:
            return redirect(url_for('user.dashboard'))

    # GET 请求：显示注册页面
    return render_template('auth/register.html')


@bp.route('/logout')
@login_required
def logout():
    """退出登录"""
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))