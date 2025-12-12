import secrets
import time

from flask import g, request

from innsight_flask.logging_config import bind_trace_id, clear_trace_id, get_logger


# Get module logger
logger = get_logger(__name__)

def _generate_trace_id() -> str:
    """Generate a unique trace ID for the request.

    Returns:
        A trace ID in the format 'req_<8 hex characters>'
        Example: 'req_7f3a9b2c'
    """
    random_hex = secrets.token_hex(4)  # 4 bytes = 8 hex characters
    return f"req_{random_hex}"

def get_trace_id():
    if 'trace_id' not in g:
        g.trace_id = _generate_trace_id()
    return g.trace_id

def get_start_time():
    if 'start_time' not in g:
        g.start_time = time.perf_counter()
    return g.start_time


def _add_trace_id():
    _trace_id = get_trace_id()

    # Bind to logging context (all logs will include trace_id)
    bind_trace_id(_trace_id)

    # Start measuring request duration
    get_start_time()


def _log_request(response):
    # Calculate duration
    _start_time = get_start_time()
    duration_ms = (time.perf_counter() - _start_time) * 1000

    # Log request completion
    logger.info(
        "API request completed",
        method=request.method,
        endpoint=request.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2)
    )

    # Add trace ID to response header
    response.headers['X-Trace-ID'] = get_trace_id()

    return response


def _clear_trace_id(exception):
    # Always clear context, even if an exception occurs
    # This prevents context leakage between requests
    clear_trace_id()


class RequestTracing:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.before_request(_add_trace_id)
        app.after_request(_log_request)
        app.teardown_request(_clear_trace_id)
