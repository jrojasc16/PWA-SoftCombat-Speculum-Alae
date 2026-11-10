"""Decoradores compartidos de control de acceso.

- ``login_redirect``: para vistas HTML, redirige a la página de login si no hay
  sesión (la identidad la resuelve Flask-Login).
- ``api_login_required``: para endpoints JSON, responde 401 (nunca redirige).
- ``role_required``: para API y panel, exige uno de los roles indicados
  (401 sin sesión, 403 con rol insuficiente) — RBAC de roles fijos del MVP
  sobre la tabla ``roles`` (PROPUESTA §4.3).
- ``role_required_html``: como ``role_required``, pero para vistas HTML del
  panel de administración (redirige al login sin sesión, 403 con rol
  insuficiente).

Ambos propagan errores de dominio (``AuthError``/``ForbiddenError``) para que
el manejador global (tarea 2.7) traduzca a respuestas consistentes.
"""

from functools import wraps

from flask import redirect, render_template, request, url_for
from flask_login import current_user

from app.shared.errors import AuthError, ForbiddenError


def login_redirect(view):
    """Vista HTML protegida: sin sesión redirige a /login (manteniendo next)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("ui.login_view", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def api_login_required(view):
    """Endpoint JSON protegido: sin sesión devuelve 401 (nunca redirige).

    Los endpoints JSON no deben responder con una redirección HTML, así que en
    lugar del ``login_required`` de Flask-Login se propaga ``AuthError`` y el
    manejador global lo traduce a ``{"error": …}`` con código 401.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            raise AuthError("Autenticación requerida.")
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


def role_required_html(*role_names: str):
    """Como ``role_required``, pero para vistas HTML del panel de administración.

    A diferencia del decorador JSON, aquí la respuesta es una **página**:

    - Sin sesión: redirige a ``/login`` (conservando ``next``), como
      ``login_redirect``.
    - Con rol insuficiente: renderiza la página de "sin permisos" con código
      **403** (el manejador global de errores solo sabe responder JSON, así que
      el panel necesita su propia salida HTML).
    """

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("ui.login_view", next=request.path))
            if current_user.role.name not in role_names:
                return (
                    render_template(
                        "sin_permisos.html",
                        roles=", ".join(role_names),
                        rol_actual=current_user.role.name,
                    ),
                    403,
                )
            return view(*args, **kwargs)

        return wrapper

    return decorator
