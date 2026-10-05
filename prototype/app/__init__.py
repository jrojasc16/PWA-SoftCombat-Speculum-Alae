"""Application Factory de Flask: crea la app, registra blueprints y extensiones por entorno."""

from pathlib import Path

from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import config_by_name
from app.extensions import bcrypt, db, login_manager, migrate


def _activar_wal_sqlite(dbapi_connection, connection_record):
    """Activa WAL en SQLite para lecturas concurrentes (propuesta §4.1)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_app(config_name="development"):
    """Crea y configura la aplicación Flask según el entorno indicado."""
    app = Flask(__name__)
    config_cls = config_by_name[config_name]
    app.config.from_object(config_cls)
    if hasattr(config_cls, "init_app"):
        config_cls.init_app(app)

    # La BD SQLite vive en instance/ (fuera del versionado); debe existir.
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    # Extensiones (ver app/extensions.py)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    # Modo WAL de SQLite al conectar (solo aplica a SQLite; otros motores lo ignoran)
    with app.app_context():
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            event.listens_for(Engine, "connect")(_activar_wal_sqlite)

    # Importar modelos para que Alembic los detecte en `flask db migrate`.
    from app.modules.iam import models as _iam_models  # noqa: F401

    # Blueprints de los módulos (capa routes → services → repositories → models)
    from app.modules.combat.routes import bp as combat_bp
    from app.modules.history.routes import bp as history_bp
    from app.modules.iam.routes import bp as iam_bp
    from app.modules.public_api.routes import bp as public_api_bp
    from app.modules.ranking.routes import bp as ranking_bp

    app.register_blueprint(iam_bp)
    app.register_blueprint(combat_bp)
    app.register_blueprint(ranking_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(public_api_bp)

    @app.shell_context_processor
    def shell_context():
        """Contexto de `flask shell`: db disponible sin importar."""
        return {"db": db}

    @app.get("/health")
    def health():
        """Comprobación mínima de vida (útil en despliegue y smoke tests)."""
        return {"status": "ok", "env": config_name}

    return app
