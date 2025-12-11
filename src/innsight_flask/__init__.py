import os

from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from . import db
from .config import AppConfig


def create_app(test_config=None):
    app_config = AppConfig.from_env()

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE_URL=os.environ.get('DATABASE_URL', 'postgresql://localhost/innsight'),
        RATELIMIT_DEFAULT='100/minute' if app_config.is_development else ["60/minute"],
    )
    app.json.ensure_ascii = False

    cors_ext = CORS(
        app,
        supports_credentials=False,
        origins="*",
        methods="*",
        allow_headers="*"
    )
    cors_ext.init_app(app)

    from .pipeline import Recommender
    app.recommender = Recommender()

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    limiter = Limiter(
        get_remote_address,
        default_limits=[app.config['RATELIMIT_DEFAULT']],
    )
    limiter.init_app(app)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # a simple page that says hello
    @app.route('/hello')
    def hello():
        return 'Hello, World!'

    from . import health
    app.register_blueprint(health.bp)

    from .api import recommend
    app.register_blueprint(recommend.bp)

    app.teardown_appcontext(db.close_db)

    @app.route('/test-db')
    def test_db():
        try:
            conn = db.get_db()
            cur = conn.cursor()
            cur.execute('SELECT 1')
            result = cur.fetchone()
            return f'Connection success: {result}'
        except Exception as e:
            return f'Connection failed: {e}'

    return app
