from flask import Blueprint, current_app
from flask_pydantic import validate

from innsight_flask.models import RecommendRequest
from innsight_flask.pipeline import Recommender


def get_recommender() -> Recommender:
    return current_app.recommender

bp = Blueprint('recommend', __name__, url_prefix='/api')

@bp.post('/recommend')
@validate()
def recommend(body: RecommendRequest):
    recommender = get_recommender()
    result = recommender.run(body.model_dump())
    return result
