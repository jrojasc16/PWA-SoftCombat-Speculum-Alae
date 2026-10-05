"""Instancias de extensiones Flask compartidas.

Se crean aquí sin inicializar (sin app) para evitar importaciones circulares:
la Application Factory (`app/__init__.py::create_app`) las vincula a la app
con `init_app(app)` en el arranque.

- ``db``: ORM SQLAlchemy (SQLite en el prototipo; migrable a MySQL/PostgreSQL).
- ``migrate``: Flask-Migrate/Alembic para migraciones de esquema.
- ``login_manager``: Flask-Login (sesiones con cookie; no JWT — ver propuesta §4.2).
- ``bcrypt``: hash de contraseñas (costo 12, RNF001; configurado en config.py).
"""

from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
