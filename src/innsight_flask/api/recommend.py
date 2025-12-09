from flask import Blueprint, request, make_response


bp = Blueprint('recommend', __name__, url_prefix='/api')

@bp.post('/recommend')
def recommend():
    data = request.get_json()
    query = data.get('query')
    res = make_response({
        'query': query
    }, 200)
    return res
