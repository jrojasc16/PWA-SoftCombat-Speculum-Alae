"""Excepciones de dominio del sistema.

Las capas de servicio lanzan estas excepciones; el manejador global
(registrado en la factory, tarea 2.7) las traduce a respuestas HTTP
consistentes. Las rutas nunca construyen respuestas de error a mano.
"""


class DomainError(Exception):
    """Error de regla de negocio (HTTP 400 por defecto)."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AuthError(DomainError):
    """Credenciales inválidas o sesión requerida (HTTP 401)."""

    status_code = 401


class ForbiddenError(DomainError):
    """Autenticado pero sin permisos para la acción (HTTP 403)."""

    status_code = 403


class NotFoundError(DomainError):
    """Recurso inexistente en el dominio (HTTP 404)."""

    status_code = 404


class ConflictError(DomainError):
    """Conflicto de estado o duplicidad (HTTP 409)."""

    status_code = 409


def register_error_handlers(app):
    """Registra el manejador global de errores de dominio en la app.

    Traduce cualquier ``DomainError`` (y subclases) a una respuesta JSON
    consistente: ``{"error": mensaje}`` con el código ``status_code`` de la
    excepción. Las vistas HTML reciben el mismo contrato en el MVP (el render
    de páginas de error llega con los templates del Sprint 7).
    """
    from flask import jsonify

    @app.errorhandler(DomainError)
    def handle_domain_error(err: DomainError):
        return jsonify({"error": err.message}), err.status_code
