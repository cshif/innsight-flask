import hashlib
import json

from flask import Blueprint, current_app, make_response, request
from flask_pydantic import validate

from innsight_flask.models import RecommendRequest
from innsight_flask.pipeline import Recommender


def get_recommender() -> Recommender:
    return current_app.recommender

def _generate_etag(content: dict) -> str:
    """Generate ETag from response content.

    Args:
        content: Dictionary representing the response content

    Returns:
        ETag string in HTTP format (quoted hash)
    """
    # Serialize to JSON with sorted keys for consistency
    json_str = json.dumps(content, sort_keys=True, ensure_ascii=False)

    # Generate MD5 hash
    hash_obj = hashlib.md5(json_str.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()

    # Return in HTTP ETag format (quoted)
    return f'"{hash_hex}"'

bp = Blueprint('recommend', __name__, url_prefix='/api')

@bp.post('/recommend')
@validate()
def recommend(body: RecommendRequest):
    recommender = get_recommender()
    result = recommender.run(body.model_dump())

    # Generate ETag from response content
    etag = _generate_etag(result)

    # Set HTTP caching headers
    response = make_response(result)
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    response.headers["ETag"] = etag

    # Check If-None-Match header
    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        should_return_304 = False

        # Check for wildcard (matches any version)
        if if_none_match.strip() == "*":
            should_return_304 = True
        else:
            # Parse multiple ETags (comma-separated)
            client_etags = [e.strip() for e in if_none_match.split(',')]
            # Check if current ETag matches any of the client's ETags
            if etag in client_etags:
                should_return_304 = True

        if should_return_304:
            # Return 304 Not Modified with no body
            res_304 = make_response("", 304)
            res_304.headers["Cache-Control"] = "no-cache, must-revalidate"
            res_304.headers["ETag"] = etag
            return res_304

    return response
