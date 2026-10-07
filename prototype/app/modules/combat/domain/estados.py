"""Máquina de estados del combate (Art. RF6/RF7 — plan Sprint 4.2).

Dominio puro: sin I/O, sin fechas, sin dependencias de la app. Las transiciones
permitidas se declaran en una única tabla para que servicios y tests compartan
la misma fuente de verdad (regla transversal 4: ``domain`` no conoce la app).

Estados (PROPUESTA §5 → módulo ``combat``)::

    PENDIENTE ──► CONFIRMADO ──► RESUELTO
        │              ▲              ▲
        │              │              │
        └──► CONFLICTO ┘──────────────┘

- ``PENDIENTE → CONFIRMADO``: dos confirmaciones coincidentes o el árbitro.
- ``PENDIENTE → CONFLICTO``: dos confirmaciones discrepantes.
- ``CONFLICTO → CONFIRMADO``: el árbitro/admin resuelve a favor de un resultado.
- Cualquier estado → ``RESUELTO``: edición manual del admin (Sprint 5.4), que
  siempre queda registrada en ``AuditLog``.
- ``RESUELTO`` es el único estado terminal.
"""

from enum import Enum

__all__ = [
    "EstadoCombate",
    "ResultadoParticipante",
    "es_terminal",
    "puede_transicionar",
    "transiciones_permitidas",
    "transicionar",
]


class EstadoCombate(str, Enum):
    """Estado de un combate dentro de la máquina de estados."""

    PENDIENTE = "PENDIENTE"
    CONFIRMADO = "CONFIRMADO"
    CONFLICTO = "CONFLICTO"
    RESUELTO = "RESUELTO"


class ResultadoParticipante(str, Enum):
    """Resultado declarado de un participante dentro del combate.

    El Art. 30 (modalidad individual) solo contempla victoria/derrota: no hay
    empate en la fórmula Elo, así que el modelo tampoco lo almacena.
    """

    VICTORIA = "VICTORIA"
    DERROTA = "DERROTA"


# Transiciones válidas: estado actual → conjunto de estados de destino.
_TRANSICIONES: dict[EstadoCombate, frozenset[EstadoCombate]] = {
    EstadoCombate.PENDIENTE: frozenset(
        {EstadoCombate.CONFIRMADO, EstadoCombate.CONFLICTO, EstadoCombate.RESUELTO}
    ),
    EstadoCombate.CONFLICTO: frozenset(
        {EstadoCombate.CONFIRMADO, EstadoCombate.RESUELTO}
    ),
    EstadoCombate.CONFIRMADO: frozenset({EstadoCombate.RESUELTO}),
    EstadoCombate.RESUELTO: frozenset(),
}


def transiciones_permitidas(actual: EstadoCombate | str) -> frozenset[EstadoCombate]:
    """Conjunto de estados a los que se puede pasar desde ``actual``.

    Raises:
        ValueError: si ``actual`` no es un estado conocido.
    """
    return _TRANSICIONES[EstadoCombate(actual)]


def puede_transicionar(actual: EstadoCombate | str, destino: EstadoCombate | str) -> bool:
    """Indica si la transición ``actual → destino`` está permitida."""
    try:
        return EstadoCombate(destino) in transiciones_permitidas(actual)
    except ValueError:
        return False


def transicionar(actual: EstadoCombate | str, destino: EstadoCombate | str) -> EstadoCombate:
    """Aplica la transición y devuelve el estado resultante.

    Raises:
        ValueError: si alguno de los estados es desconocido o la transición
            está prohibida (el mensaje lista las transiciones válidas).
    """
    origen = EstadoCombate(actual)
    nuevo = EstadoCombate(destino)
    permitidas = transiciones_permitidas(origen)
    if nuevo not in permitidas:
        validas = ", ".join(sorted(e.value for e in permitidas)) or "(ninguna: estado terminal)"
        raise ValueError(
            f"Transición inválida: {origen.value} → {nuevo.value}. Permitidas: {validas}."
        )
    return nuevo


def es_terminal(estado: EstadoCombate | str) -> bool:
    """``True`` si el estado no admite ninguna transición posterior."""
    return not transiciones_permitidas(estado)
