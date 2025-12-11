import os


class SecurityHeaders:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.after_request(self._add_headers)

    def _add_headers(self, response):
        # Add X-Content-Type-Options header
        response.headers['X-Content-Type-Options'] = 'nosniff'

        # Add X-Frame-Options header
        response.headers['X-Frame-Options'] = 'DENY'

        # Add Referrer-Policy header
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Add Strict-Transport-Security header (only in production)
        env = os.getenv('ENV', 'local')  # Default to 'local' if not set
        if env == 'prod':
            response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains'

        # Add Content-Security-Policy header (strict API policy)
        response.headers['Content-Security-Policy'] = 'default-src "none"; frame-ancestors "none"'

        # Add Permissions-Policy header (disable all browser features)
        response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=(), ambient-light-sensor=()'

        # Add Cross-Origin-Opener-Policy header
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'

        # Add Cross-Origin-Resource-Policy header
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'

        return response
