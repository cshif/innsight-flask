from flask import Blueprint
from flask_pydantic import validate

from innsight_flask.models import RecommendRequest

bp = Blueprint('recommend', __name__, url_prefix='/api')

@bp.post('/recommend')
@validate()
def recommend(body: RecommendRequest):
    query = body.query
    return query
