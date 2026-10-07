"""Orquestación del recálculo on-write (Unit of Work transaccional, idempotente).

RNF008: cuando un combate pasa a un estado terminal (``CONFIRMADO`` o
``RESUELTO``) sus dos participantes ven su índice actualizado **en la misma
transacción** que el cambio de estado — nunca a mediano plazo.

Garantías:

- **Idempotencia:** si ``combat.processed`` ya es ``True`` el servicio no hace
  nada (regla transversal 2: un combate jamás se reprocesa).
- **Atomicidad:** todo el cálculo, la escritura de ``Rating``/``RatingHistory``
  y la marca ``processed`` se confirman con **un único commit**; cualquier
  excepción revierte la sesión entera (sin estados parciales).
- Los índices se crean con ``RATING_INICIAL`` (1500) el día que un jugador
  participa en su primer combate de ranking; el percentil se mide sobre los
  índices vivos de la comunidad.

El cálculo en sí es puro y vive en ``domain/elo.py``; aquí solo hay
coordinación de persistencia (regla transversal 4: capas routes → services →
repositories → models).
"""

from datetime import datetime, timezone

from app.modules.combat.domain.estados import EstadoCombate, ResultadoParticipante
from app.modules.combat.models import Combat
from app.modules.combat.repositories import CombatRepository
from app.modules.ranking.domain.constants import RATING_INICIAL
from app.modules.ranking.domain.elo import Resultado, resolver_duelo
from app.modules.ranking.models import Rating, RatingHistory
from app.modules.ranking.repositories import RatingHistoryRepository, RatingRepository
from app.shared.errors import DomainError, NotFoundError

# Estados desde los cuales el combate ya cuenta para el ranking.
ESTADOS_PROCESABLES = frozenset({EstadoCombate.CONFIRMADO, EstadoCombate.RESUELTO})


def _utc_ahora() -> datetime:
    """Ahora en UTC como datetime naive (SQLite no almacena husos)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _percentil(user_id: int, puntos: dict[int, float]) -> float:
    """Percentil del jugador en su comunidad, medido **desde el fondo**.

    Regla de dominio cerrada en el Sprint 3: ``(jugadores por debajo) / N × 100``
    y el **único líder** de la tabla se especializa a ``100`` (de ahí que su
    ``x`` sea 0.2). El cálculo pertenece al servicio, no al dominio puro.
    """
    if not puntos:
        return 0.0
    yo = puntos[user_id]
    maximo = max(puntos.values())
    if yo == maximo and sum(1 for v in puntos.values() if v == yo) == 1:
        return 100.0
    abajo = sum(1 for v in puntos.values() if v < yo)
    return abajo / len(puntos) * 100.0


def _rating_de(
    ratings: dict[int, Rating], user_id: int, community_id: int
) -> Rating:
    """Índice del jugador en el mapa, creándolo con el valor inicial si falta."""
    rating = ratings.get(user_id)
    if rating is None:
        rating = Rating(
            user_id=user_id,
            community_id=community_id,
            points=RATING_INICIAL,
            matches_played=0,
        )
        ratings[user_id] = rating
    return rating


def procesar_duelo(combat: Combat, ratings: dict[int, Rating]) -> None:
    """Aplica el resultado Elo de un combate terminal sobre ``ratings``.

    Escribe en la sesión los dos ``Rating`` actualizados y sus dos snapshots en
    ``RatingHistory``. **No hace commit**: el Unit of Work lo cierra el
    servicio llamante (``process_confirmed_combat`` o ``recalculate_full``).

    Raises:
        DomainError: el combate no tiene exactamente 2 participantes o su
            resultado declarado no es una victoria/derrota inequívoca.
    """
    participantes = list(combat.participants)
    if len(participantes) != 2:
        raise DomainError(
            f"El combate {combat.id} no tiene exactamente 2 participantes "
            f"(encontrados: {len(participantes)})."
        )

    victorias = [p for p in participantes if p.result is ResultadoParticipante.VICTORIA]
    derrotas = [p for p in participantes if p.result is ResultadoParticipante.DERROTA]
    if len(victorias) != 1 or len(derrotas) != 1:
        raise DomainError(
            f"El combate {combat.id} no tiene un resultado válido: se espera "
            "una victoria y una derrota."
        )

    a, b = participantes[0], participantes[1]
    rating_a = _rating_de(ratings, a.user_id, combat.community_id)
    rating_b = _rating_de(ratings, b.user_id, combat.community_id)

    # Percentiles sobre la tabla **antes** de aplicar este combate.
    puntos = {uid: r.points for uid, r in ratings.items()}
    percentil_a = _percentil(a.user_id, puntos)
    percentil_b = _percentil(b.user_id, puntos)

    ganador = victorias[0]
    resultado = (
        Resultado.VICTORIA_A if ganador.user_id == a.user_id else Resultado.VICTORIA_B
    )

    duelo = resolver_duelo(
        rating_a.points,
        rating_b.points,
        rating_a.matches_played,
        percentil_a,
        rating_b.matches_played,
        percentil_b,
        resultado,
    )

    for jugador, nuevo, k, percentil in (
        (a, duelo.nuevo_a, duelo.k_a, percentil_a),
        (b, duelo.nuevo_b, duelo.k_b, percentil_b),
    ):
        rating = ratings[jugador.user_id]
        puntos_antes = rating.points
        rating.points = nuevo
        rating.matches_played += 1
        rating.updated_at = _utc_ahora()
        RatingRepository.add(rating)
        RatingHistoryRepository.add(
            RatingHistory(
                combat_id=combat.id,
                user_id=jugador.user_id,
                community_id=combat.community_id,
                points_before=puntos_antes,
                points_after=nuevo,
                matches_played=rating.matches_played,
                k=k,
                percentil=percentil,
            )
        )


def process_confirmed_combat(combat_id, *, commit: bool = True) -> bool:
    """Recalcula los índices de un combate recién cerrado (RNF008).

    Args:
        combat_id: combate terminal a procesar.
        commit: ``True`` (por defecto) cierra la transacción aquí; el hook del
            módulo combate lo llama con ``False`` para que el único commit sea
            el de ``confirm_combat``/``admin_edit_result``.

    Returns:
        ``True`` si el combate se procesó ahora; ``False`` si ya estaba
        procesado (idempotencia: jamás se reprocesa).

    Raises:
        NotFoundError: combate inexistente (404).
        DomainError: combate aún no terminal (400).
    """
    try:
        combat = CombatRepository.get_by_id(combat_id)
        if combat is None:
            raise NotFoundError(f"No existe el combate {combat_id}.")
        if combat.processed:
            return False
        if combat.status not in ESTADOS_PROCESABLES:
            raise DomainError(
                f"El combate {combat.id} está en {combat.status.value}: solo se "
                "procesan combates confirmados o resueltos."
            )

        ratings = {r.user_id: r for r in RatingRepository.listar(combat.community_id)}
        procesar_duelo(combat, ratings)
        combat.processed = True

        if commit:
            RatingRepository.save()
    except Exception:
        if commit:
            RatingRepository.rollback()
        raise
    return True


def recalculate_full(community_id, *, commit: bool = True) -> int:
    """Reconstruye los índices de una comunidad desde su historial (RF9/RNF008).

    Se usa en dos casos: la edición manual de un admin (que puede cambiar un
    resultado ya procesado) y el recálculo manual del panel (tarea 6.4).

    Pasos, todo en **una sola transacción**:

    1. Borra ``RatingHistory`` y ``Rating`` de la comunidad (se reconstruyen).
    2. Recorre los combates terminales **ordenados cronológicamente**.
    3. Aplica cada duelo con ``domain/elo.py`` y marca ``processed = True``.
    4. Commit único (o el de la llamada si ``commit=False``).

    Args:
        community_id: comunidad a reconstruir.
        commit: ``False`` cuando el Unit of Work lo cierra otro servicio.

    Returns:
        Número de combates reprocesados.

    Raises:
        DomainError: algún combate terminal no tiene resultado válido.
    """
    try:
        RatingHistoryRepository.borrar_de_comunidad(community_id)
        RatingRepository.borrar_de_comunidad(community_id)

        ratings: dict[int, Rating] = {}
        procesados = 0
        for combat in CombatRepository.listar_terminales(community_id):
            procesar_duelo(combat, ratings)
            combat.processed = True
            procesados += 1

        if commit:
            RatingRepository.save()
    except Exception:
        if commit:
            RatingRepository.rollback()
        raise
    return procesados

