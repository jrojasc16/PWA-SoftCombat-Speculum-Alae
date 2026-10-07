"""Constantes del reglamento nacional de SoftCombat 2021 — Art. 30 (págs. 13–15).

Fuente normativa: ``documentation/reglamento_nacional_softcombat_2021.md``,
apartado *Art. 30 - Ranking → Fórmulas*. Allí se define la constante ``k``:

    k = t · x

- ``t`` depende del **número de combates de ranking** del jugador (veteranía).
- ``x`` depende de la **posición (percentil) del jugador en el ranking**.

Módulo **puro**: sin I/O, sin fechas, sin Flask ni SQLAlchemy (regla de dominio
del plan de desarrollo, tarea 3.3). Es la única fuente de verdad de las tablas;
``app/shared/constants.py`` las reexporta para el resto de la aplicación.

Decisiones documentadas sobre inconsistencias del reglamento (cerradas con el
usuario antes de implementar):

1. **Tramo 61–80 combates.** La tabla publicada cubre ``41–60 → 2.5`` y
   ``Más de 80 → 0.5``, dejando 61–80 sin asignar. Se resuelve repitiendo el
   último valor conocido (``2.5``), sin inventar una cifra nueva. Por eso el
   tramo de entrada 41 abarca de hecho 41–80.
2. **Ejemplo trabajado (págs. 13–15).** Los valores del ejemplo no concuerdan
   con las tablas (``25 combates → t = 15`` frente a ``21–40 → 5``;
   ``64 combates → t = 5`` frente a ``41–60 → 2.5``; ``76–84.9 % → x = 1``
   frente a ``0.5``). Prevalecen las **tablas** (normativas); el ejemplo se
   trata como ilustrativo y así se documenta en los tests.
"""

# Índice inicial asignado al ingresar al ranking (Art. 30 → "Fórmulas").
RATING_INICIAL: float = 1500.0

# Tabla de ``t`` por número de combates de ranking.
# Tuplas (límite_inferior_inclusivo, t); se aplica el primer tramo cuyo
# límite inferior sea <= combates.
#   0–10 → 10 | 11–20 → 7.5 | 21–40 → 5 | 41–80 → 2.5 | 81+ → 0.5
TABLA_T: tuple[tuple[int, float], ...] = (
    (0, 10.0),
    (11, 7.5),
    (21, 5.0),
    (41, 2.5),
    (81, 0.5),
)

# Tabla de ``x`` por percentil en el ranking (0 % = fondo de la tabla,
# 100 % = primera posición).
#   0 → 2 | 20 → 1.8 | 37 → 1.6 | 52 → 0.7 | 65 → 0.6
#   76 → 0.5 | 85 → 0.4 | 92 → 0.3 | 100 → 0.2
TABLA_X: tuple[tuple[float, float], ...] = (
    (0.0, 2.0),
    (20.0, 1.8),
    (37.0, 1.6),
    (52.0, 0.7),
    (65.0, 0.6),
    (76.0, 0.5),
    (85.0, 0.4),
    (92.0, 0.3),
    (100.0, 0.2),
)
