"""DTO y caché en memoria del ranking público (RNF004: <500 ms, cacheable).

``GET /api/ranking`` es **público** (sin login) y no puede exponer datos
sensibles: el DTO solo lleva posición, nombre, puntos y nº de combates —
nunca emails ni ids internos.

La caché es un dict en memoria con TTL configurable
(``RANKING_CACHE_TTL`` segundos, ver ``app/config.py``; 0 en pruebas) que se
invalida tras **cada** recálculo (confirmación, edición admin o recálculo
manual), de modo que el ranking nunca sirve índices obsoletos.
"""

import threading
import time

from flask import current_app

from app.modules.ranking.repositories import RatingRepository

_LOCK = threading.Lock()
_CACHE: dict[tuple, tuple[dict, float]] = {}


def ttl_cache() -> float:
    """TTL configurado para el entorno actual (segundos).

    Lo usa la ruta para emitir la cabecera ``Cache-Control`` con el mismo
    valor que respeta la caché en memoria.
    """
    return float(current_app.config.get("RANKING_CACHE_TTL", 300))


def invalidar_cache() -> None:
    """Vacía toda la caché del ranking público (idempotente)."""
    with _LOCK:
        _CACHE.clear()


def _consultar(community_id: int, page: int, per_page: int) -> dict:
    """Consulta real a la BD y construcción del DTO paginado."""
    ratings = RatingRepository.listar(community_id)
    total = len(ratings)
    inicio = (page - 1) * per_page
    pagina = ratings[inicio : inicio + per_page]
    return {
        "community_id": community_id,
        "page": page,
        "per_page": per_page,
        "total": total,
        "items": [
            {
                # La posición es global (no se reinicia en cada página).
                "position": inicio + indice + 1,
                "name": rating.user.name,
                "points": rating.points,
                "matches_played": rating.matches_played,
            }
            for indice, rating in enumerate(pagina)
        ],
    }


def ranking_publico(community_id: int, page: int, per_page: int) -> dict:
    """Ranking paginado de la comunidad, sirviendo de la caché si está viva.

    Args:
        community_id: comunidad (RNF006).
        page: página 1-based.
        per_page: tamaño de página.

    Returns:
        DTO público con ``position``/``name``/``points``/``matches_played``.
    """
    ttl = ttl_cache()
    if ttl <= 0:
        return _consultar(community_id, page, per_page)

    clave = (community_id, page, per_page)
    ahora = time.monotonic()
    with _LOCK:
        entrada = _CACHE.get(clave)
        if entrada is not None and entrada[1] > ahora:
            return entrada[0]

    payload = _consultar(community_id, page, per_page)
    with _LOCK:
        _CACHE[clave] = (payload, ahora + ttl)
    return payload
