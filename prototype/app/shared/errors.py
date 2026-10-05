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
