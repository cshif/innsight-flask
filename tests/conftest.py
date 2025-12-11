import pytest
import warnings
from innsight_flask import create_app

@pytest.fixture
def app():
    """Create app for testing"""
    app = create_app({
        'TESTING': True,
        'RATELIMIT_DEFAULT': '3/minute',
    })
    yield app

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture(autouse=True)
def ignore_limiter_warning():
    warnings.filterwarnings('ignore', message='using in-memory storage')
