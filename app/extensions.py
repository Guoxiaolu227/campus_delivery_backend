# Flask extensions initialized here
"""
扩展初始化
- 在这里创建扩展实例（但不绑定 app）
- 实际绑定在 create_app() 中通过 .init_app(app) 完成
- 这样做可以避免循环导入的问题
"""

from flask_sqlalchemy import SQLAlchemy

# 创建数据库实例（此时还没有绑定任何 Flask 应用）
db = SQLAlchemy()