"""Dominio puro del módulo combate: valores de estados y resultados.

Sin Flask ni SQLAlchemy: los modelos de ``combat/models.py`` importan de aquí
(los módulos dependen del dominio, nunca al revés).
"""

from app.modules.combat.domain.estados import EstadoCombate, ResultadoParticipante

__all__ = ["EstadoCombate", "ResultadoParticipante"]
