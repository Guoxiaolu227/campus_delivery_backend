from flask import Blueprint

bp = Blueprint('rider', __name__)

from app.rider import routes  # noqa