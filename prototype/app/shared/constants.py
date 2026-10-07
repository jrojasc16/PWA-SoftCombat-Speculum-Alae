"""Constantes del reglamento nacional de SoftCombat 2021 (págs. 13-15): valores de k, percentiles.

La fuente de verdad es el módulo puro ``app.modules.ranking.domain.constants``
(parte del dominio Elo, sin dependencias de Flask ni de la BD). Este módulo las
reexporta para que el resto de la aplicación (``shared``, ``services``, rutas)
pueda importarlas sin acoplarse al paquete ``ranking``.

Ver el docstring de ``domain/constants.py`` para las decisiones documentadas
sobre las inconsistencias del reglamento (tramo 61–80 y ejemplo de las págs. 13–15).
"""

from app.modules.ranking.domain.constants import RATING_INICIAL, TABLA_T, TABLA_X

__all__ = ["RATING_INICIAL", "TABLA_T", "TABLA_X"]
