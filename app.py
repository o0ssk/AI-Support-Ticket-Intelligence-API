"""
app.py — Flask application factory and entry point.

Why an application factory (create_app)?
  - Testing: tests call create_app("testing") to get an isolated app instance
  - Flexibility: different configs for dev / prod / test without code changes
  - Avoids circular imports: extensions are created without an app,
    then initialised with one inside create_app()

This file is also the entry point when you run: python app.py
"""

from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import get_config, Config
from models.ticket import db
from routes.tickets import tickets_bp
from utils.logger import logger, setup_logger


def create_app(config_object: Config | None = None) -> Flask:
    """
    Create, configure, and return the Flask application.

    Args:
        config_object: A config class to use. If None, reads FLASK_ENV
                       from the environment to determine the config.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__, instance_relative_config=True)

    # ------------------------------------------------------------------
    # 1. Load Configuration
    # ------------------------------------------------------------------
    if config_object is None:
        config_object = get_config()

    app.config.from_object(config_object)

    # Initialise logger now that we know if we're in debug mode
    setup_logger(debug=app.config.get("DEBUG", False))
    logger.info("Starting SupportFlow with config: %s", config_object.__name__)

    # ------------------------------------------------------------------
    # 2. Initialise Extensions
    # ------------------------------------------------------------------

    # SQLAlchemy — bind the db instance to this app
    db.init_app(app)

    # Rate Limiter — uses memory storage by default (Redis in production)
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[app.config.get("RATELIMIT_DEFAULT", "10 per minute")],
        storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://"),
    )

    # Apply rate limiter to the create ticket endpoint specifically
    # (it calls the AI which costs money/quota)
    # The limiter is applied via decorator in the route, but we expose
    # the limiter here so routes can use it if needed.
    app.limiter = limiter

    # ------------------------------------------------------------------
    # 3. Create Database Tables
    # ------------------------------------------------------------------
    with app.app_context():
        db.create_all()
        logger.info("Database tables created/verified.")

    # ------------------------------------------------------------------
    # 4. Register Blueprints
    # ------------------------------------------------------------------
    # All ticket routes are prefixed with /api
    app.register_blueprint(tickets_bp, url_prefix="/api")
    logger.info("Blueprints registered.")

    # ------------------------------------------------------------------
    # 5. Register Global Error Handlers
    # ------------------------------------------------------------------
    # These catch errors that bubble up from anywhere in the app.
    # They ensure we ALWAYS return JSON (never an HTML error page).

    @app.errorhandler(400)
    def bad_request(e):
        logger.warning("400 Bad Request: %s", str(e))
        return jsonify({"error": "Bad request."}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "The requested resource was not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        logger.warning("Rate limit exceeded from IP: %s", get_remote_address())
        return jsonify({"error": "Too many requests. Please slow down."}), 429

    @app.errorhandler(500)
    def internal_error(e):
        # Log the real error internally, return a safe message to the client
        logger.error("500 Internal Server Error: %s", str(e))
        return jsonify({"error": "An internal server error occurred."}), 500

    # ------------------------------------------------------------------
    # 6. Health Check Endpoint
    # ------------------------------------------------------------------
    @app.route("/health")
    def health():
        """
        Simple liveness check.
        Returns 200 if the server is running and DB is reachable.
        Used by load balancers, Docker health checks, and monitoring tools.
        """
        try:
            # Quick DB connectivity check — just count rows in the tickets table
            ticket_count = db.session.execute(
                db.select(db.func.count()).select_from(
                    db.text("tickets")
                )
            ).scalar()
        except Exception:
            ticket_count = None

        return jsonify({
            "status": "ok",
            "service": "AI Support Ticket Intelligence API",
            "database": "connected" if ticket_count is not None else "error",
        }), 200

    logger.info("SupportFlow application ready.")
    return app


# ─── Entry Point ─────────────────────────────────────────────────────────────
# This block only runs when you execute: python app.py
# When using gunicorn in production, gunicorn calls create_app() directly.

if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(
        host="0.0.0.0",
        port=5000,
        debug=flask_app.config.get("DEBUG", False),
    )
