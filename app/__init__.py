import os
from flask import Flask
from metrics import calculate_bio_week
from config import Config
from app.database import db
from app.extensions import login_manager, migrate, csrf, limiter, cache

def create_app(config_class=Config):
    app = Flask(__name__)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)

    # Ensure upload and instance folders exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, '..', 'instance'), exist_ok=True)

    # Register handlers
    from app.handlers import register_error_handlers, register_template_filters, register_context_processors, register_request_hooks
    register_error_handlers(app)
    register_template_filters(app)
    register_context_processors(app)
    register_request_hooks(app)

    # Register Routes
    from app.routes.auth import register_auth_routes
    from app.routes.main import register_main_routes
    from app.routes.production import register_production_routes
    from app.routes.hatchery import register_hatchery_routes
    from app.routes.health import register_health_routes
    from app.routes.admin import register_admin_routes
    from app.routes.api import register_api_routes
    from app.routes.presentation import presentation_bp
    from app.routes.broiler import broiler_bp
    from app.routes.presentation_views import presentation_views_bp

    register_auth_routes(app)
    register_main_routes(app)
    register_production_routes(app)
    register_hatchery_routes(app)
    register_health_routes(app)
    register_admin_routes(app)
    register_api_routes(app)
    app.register_blueprint(presentation_bp)
    app.register_blueprint(broiler_bp)
    app.register_blueprint(presentation_views_bp)


    import logging
    from logging.handlers import RotatingFileHandler
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/erp_slh.log', maxBytes=102400, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)

    # Configure root logger
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.INFO)

    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('ERP SLH startup')


    with app.app_context():
        @app.context_processor
        def utility_processor():
            from app.utils import get_dashboard_url
            return dict(calculate_bio_week=calculate_bio_week, get_dashboard_url=get_dashboard_url)

    return app
