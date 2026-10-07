"""Dominio puro del módulo combate: máquina de estados y resultados.

Sin Flask ni SQLAlchemy: los modelos de ``combat/models.py`` importan de aquí
(los módulos dependen del dominio, nunca al revés).
"""

from app.modules.combat.domain.estados import (
    EstadoCombate,
    ResultadoParticipante,
    es_terminal,
    puede_transicionar,
    transiciones_permitidas,
    transicionar,
)

__all__ = [
    "EstadoCombate",
    "ResultadoParticipante",
    "es_terminal",
    "puede_transicionar",
    "transiciones_permitidas",
    "transicionar",
]
