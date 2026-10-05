"""Configuración por entorno del monolito Flask (prototipo Speculum-Alae).

Clases:
- ``Config``: valores base comunes.
- ``DevelopmentConfig``: desarrollo local (SQLite en ``instance/``, debug).
- ``TestingConfig``: pruebas (SQLite en memoria, sin seguridad de cookies).
- ``ProductionConfig``: producción (SECRET_KEY obligatoria por entorno, cookies seguras).

La factory selecciona la clase con ``create_app(config_name)`` usando el
mapa ``config_by_name``.
"""

import os
from pathlib import Path

# Directorio instance/ (BD SQLite por entorno); queda fuera del versionado.
INSTANCE_DIR = Path(__file__).resolve().parent.parent / "instance"


class Config:
    """Configuración base compartida por todos los entornos."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-cambiar-en-produccion")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # RNF001: bcrypt con costo 12 para hash de contraseñas.
    BCRYPT_LOG_ROUNDS = 12
    # TTL (segundos) de la caché en memoria del endpoint público GET /api/ranking.
    RANKING_CACHE_TTL = 300
    # Cookies de sesión (Flask-Login); Secure se activa solo en producción (HTTPS).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False


class DevelopmentConfig(Config):
    """Desarrollo local: SQLite en archivo dentro de instance/, debug activo."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'app.db'}"
    )


class TestingConfig(Config):
    """Pruebas con pytest: SQLite en memoria, hashing rápido, cookies sin Secure."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Costo reducido SOLO en tests para que la suite sea rápida;
    # el valor efectivo de 12 se verifica con un test dedicado (Sprint 2).
    BCRYPT_LOG_ROUNDS = 4
    RANKING_CACHE_TTL = 0  # sin caché en pruebas
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Producción (PythonAnywhere): HTTPS obligatorio y SECRET_KEY del entorno."""

    SESSION_COOKIE_SECURE = True  # solo HTTPS (RNF001)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'app.db'}"
    )

    @classmethod
    def init_app(cls, app):
        # Falla explícita si falta la clave secreta real en producción.
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError(
                "SECRET_KEY no definida: es obligatoria en producción (variable de entorno)."
            )


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
