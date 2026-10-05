"""Decoradores compartidos de control de acceso.

- ``login_redirect``: para vistas HTML, redirige a la página de login si no hay
  sesión (la identidad la resuelve Flask-Login).
- ``role_required``: para API y panel, exige uno de los roles indicados
  (401 sin sesión, 403 con rol insuficiente) — RBAC de roles fijos del MVP
  sobre la tabla ``roles`` (PROPUESTA §4.3).

Ambos propagan errores de dominio (``AuthError``/``ForbiddenError``) para que
el manejador global (tarea 2.7) traduzca a respuestas consistentes.
"""

from functools import wraps

from flask import redirect, request, url_for
from flask_login import current_user

from app.shared.errors import AuthError, ForbiddenError


def login_redirect(view):
    """Vista HTML protegida: sin sesión redirige a /login (manteniendo next)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("iam.login_view", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def role_required(*role_names: str):
    """Exige sesión iniciada y uno de los roles dados (p. ej. 'admin', 'super_admin')."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                raise AuthError("Autenticación requerida.")
            if current_user.role.name not in role_names:
                raise ForbiddenError("No tienes permisos para esta acción.")
            return view(*args, **kwargs)

        return wrapper

    return decorator
