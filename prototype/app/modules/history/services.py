"""Historial de partidas del usuario autenticado (RF10).

Para cada combate en el que participó devuelve el resultado, el rival y la
**variación de su índice** (``points_before`` → ``points_after``) tomada del
snapshot que escribe el recálculo on-write (Sprint 6.2). Los combates que
aún no están procesados (``PENDIENTE``/``CONFLICTO``) no tienen snapshot y se
devuelven con ``rating: null``.
"""

from app.modules.history.repositories import HistorialRepository
from app.modules.ranking.repositories import RatingRepository


def _rival(combat, user_id: int):
    """Participante que no soy yo (``None`` si el combate quedó mal formado)."""
    return next((p for p in combat.participants if p.user_id != user_id), None)


def _item(combat, user_id: int, snapshot) -> dict:
    """DTO de un combate del historial (sin emails ni datos ajenos)."""
    propio = next((p for p in combat.participants if p.user_id == user_id), None)
    rival = _rival(combat, user_id)
    return {
        "combat_id": combat.id,
        "played_at": combat.played_at.isoformat(),
        "status": combat.status.value,
        "winner_id": combat.ganador_id,
        "opponent": (
            {"id": rival.user_id, "name": rival.user.name} if rival else None
        ),
        "result": propio.result.value if propio else None,
        "rating": (
            {
                "points_before": snapshot.points_before,
                "points_after": snapshot.points_after,
                "delta": snapshot.points_after - snapshot.points_before,
                "matches_played": snapshot.matches_played,
                "k": snapshot.k,
                "percentil": snapshot.percentil,
            }
            if snapshot is not None
            else None
        ),
    }


def historial_de_usuario(user_id: int, community_id: int, page: int, per_page: int) -> dict:
    """Historial paginado de un usuario, del combate más reciente al más antiguo.

    Args:
        user_id: jugador (siempre ``current_user`` en la ruta).
        community_id: comunidad del jugador (RNF006).
        page: página 1-based.
        per_page: tamaño de página.

    Returns:
        ``{"page", "per_page", "total", "rating", "items"}`` donde ``rating``
        es el índice actual del jugador (o ``None`` si nunca jugó).
    """
    combates = HistorialRepository.combates_de_usuario(user_id, community_id)
    total = len(combates)
    inicio = (page - 1) * per_page
    pagina = combates[inicio : inicio + per_page]

    snapshots = HistorialRepository.snapshots_de_usuario(
        user_id, [c.id for c in pagina]
    )
    rating = RatingRepository.get(user_id, community_id)

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "rating": (
            {"points": rating.points, "matches_played": rating.matches_played}
            if rating is not None
            else None
        ),
        "items": [_item(c, user_id, snapshots.get(c.id)) for c in pagina],
    }
