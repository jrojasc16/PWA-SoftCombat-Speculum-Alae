"""Valores de dominio del combate (Sprint 4.1): estados y resultados.

Dominio puro: sin I/O, sin fechas, sin dependencias de la app. Los modelos de
``combat/models.py`` importan estos enums para tipar sus columnas (los módulos
dependen del dominio, nunca al revés). La máquina de estados completa —
transiciones permitidas y rechazo de las inválidas — llega en la tarea 4.2.
"""

from enum import Enum

__all__ = ["EstadoCombate", "ResultadoParticipante"]


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
