"""Endpoint público GET /api/ranking (sin auth, preparado para API key).

RNF004: consulta **pública** del ranking, cacheable y por debajo de 500 ms
con 100 usuarios concurrentes. El control de acceso por API key queda previsto
para cuando exista un plan de API (hoy solo se documenta en el contrato OpenAPI).

Las rutas solo adaptan HTTP ↔ servicios (regla transversal 4): la caché, la
consulta y la paginación viven en ``public_api/services.py``.
"""

from flask import Blueprint, jsonify, request

from app.modules.public_api import services
from app.shared.errors import DomainError

bp = Blueprint("public_api", __name__)

# Límites de paginación: respuesta acotada siempre (RNF004).
_POR_DEFECTO = 50
_MAXIMO = 100


def _entero(nombre: str, valor, defecto: int, minimo: int, maximo: int | None = None) -> int:
    """Convierte y valida un parámetro de consulta entero.

    Raises:
        DomainError: valor no numérico o fuera de rango (400).
    """
    if valor is None:
        return defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise DomainError(f"El parámetro '{nombre}' debe ser un entero.") from exc
    if numero < minimo or (maximo is not None and numero > maximo):
        rango = f"entre {minimo} y {maximo}" if maximo else f">= {minimo}"
        raise DomainError(f"El parámetro '{nombre}' debe ser {rango}.")
    return numero


@bp.get("/api/ranking")
def api_ranking():
    """Ranking público de la comunidad, paginado y cacheado.

    Query string:

    - ``community_id`` (por defecto 1) — RNF006, aislamiento por comunidad.
    - ``page`` (por defecto 1) y ``per_page`` (por defecto 50, máximo 100).

    Respuesta: ``{"community_id", "page", "per_page", "total", "items"}`` con
    ``items`` de ``{"position", "name", "points", "matches_played"}`` — nunca
    emails ni ids internos. Cabecera ``Cache-Control: public, max-age=<TTL>``.
    """
    community_id = _entero("community_id", request.args.get("community_id"), 1, 1)
    page = _entero("page", request.args.get("page"), 1, 1)
    per_page = _entero(
        "per_page", request.args.get("per_page"), _POR_DEFECTO, 1, _MAXIMO
    )

    payload = services.ranking_publico(community_id, page, per_page)
    respuesta = jsonify(payload)
    respuesta.headers["Cache-Control"] = f"public, max-age={int(services.ttl_cache())}"
    return respuesta, 200
