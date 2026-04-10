"""
项目启动入口

使用方法:
    方式1（命令行）: python run.py
    方式2（PyCharm）: 右键 run.py → Run
"""

from app import create_app

# 调用应用工厂创建 Flask 实例
app = create_app()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🍜 校园外卖配送系统启动中...")
    print("=" * 60)
    print(f"📡 访问地址: http://127.0.0.1:5000")
    print(f"📡 按 Ctrl+C 停止服务")
    print("=" * 60 + "\n")

    # debug=True: 开发模式，代码修改后自动重启
    # host='0.0.0.0': 允许局域网内其他设备访问
    app.run(debug=True, host='0.0.0.0', port=5000)
