"""Casos de ejemplo calculados a mano desde el reglamento (Sprint 3.5).

Reproduce paso a paso los ejercicios del Art. 30 (págs. 13–15) comentando las
fórmulas y las páginas, y documenta la discrepancia entre el ejemplo ilustrativo
y las tablas normativas (decisión cerrada: **prevalecen las tablas**).
"""

from __future__ import annotations

import pytest

from app.modules.ranking.domain.elo import (
    Resultado,
    expected_score,
    k_factor,
    new_ratings,
    t_factor,
    x_factor,
)

VICTORIA_A = Resultado.VICTORIA_A
VICTORIA_B = Resultado.VICTORIA_B


def test_ejemplo_manual_indices_iguales():
    """Caso 1 (Art. 30 → Fórmulas): dos debutantes a 1500 con k = 16.

    Paso 1 — ``p_A = 1 / (1 + 10^((1500 − 1500)/400)) = 1 / 2 = 0.5``.
    Paso 2 — ``ΔI_A = 1500 + 16·(1 − 0.5) = 1508``.
    Paso 3 — ``ΔI_B = 1500 + 16·(0 − 0.5) = 1492``.
    Los dos resultados se obtienen sin redondeos intermedios.
    """
    nuevo_a, nuevo_b = new_ratings(1500, 1500, VICTORIA_A, 16.0, 16.0)
    assert nuevo_a == pytest.approx(1508.0)
    assert nuevo_b == pytest.approx(1492.0)


def test_ejemplo_manual_del_reglamento_A_vence_a_B():
    """Caso 2 (págs. 13–15): A (1420, k = 27) vence a B (1632, k = 5).

    Paso 1 — ``p_A = 1 / (1 + 10^((1632 − 1420)/400))``.
    Con precisión completa ``p_A = 0.22787…`` (el reglamento escribe 0.23).
    Paso 2 — ``ΔI_A = 1420 + 27·(1 − 0.22787) = 1440.85``
    (el reglamento publica 1440.79 porque redondea ``p_v`` a 2 decimales).
    Paso 3 — ``ΔI_B = 1632 + 5·(0 − 0.77213) = 1628.14``
    (el reglamento publica 1628.15).
    """
    p_a = expected_score(1420, 1632)
    nuevo_a, nuevo_b = new_ratings(1420, 1632, VICTORIA_A, 27.0, 5.0)

    # Cálculo a mano con la fórmula completa (sin redondeos intermedios).
    assert nuevo_a == pytest.approx(1420 + 27 * (1 - p_a))
    assert nuevo_b == pytest.approx(1632 + 5 * (0 - (1 - p_a)))

    # Coincidencia con los valores publicados (diferencia < 0.1 causada porque
    # el reglamento redondea p_v a 2 decimales antes de sustituir).
    assert abs(nuevo_a - 1440.79) < 0.1
    assert abs(nuevo_b - 1628.15) < 0.1

    # Reproducción exacta del ejemplo cuando se usa p redondeado a 2 decimales.
    assert round(1420 + 27 * (1 - round(p_a, 2)), 2) == 1440.79
    assert round(1632 + 5 * (0 - round(1 - p_a, 2)), 2) == 1628.15


def test_ejemplo_manual_del_reglamento_B_vence_a_A():
    """Caso 3 (págs. 13–15): ahora B vence a A con los mismos índices y k.

    Paso 1 — ``p_A`` es el mismo: 0.22787… y ``p_B = 1 − p_A = 0.77213…``.
    Paso 2 — ``ΔI_A = 1420 + 27·(0 − 0.22787) = 1413.85``
    (el reglamento publica 1413.79).
    Paso 3 — ``ΔI_B = 1632 + 5·(1 − 0.77213) = 1633.14``
    (el reglamento publica 1633.15).
    """
    p_a = expected_score(1420, 1632)
    nuevo_a, nuevo_b = new_ratings(1420, 1632, VICTORIA_B, 27.0, 5.0)
    assert nuevo_a == pytest.approx(1420 + 27 * (0 - p_a))
    assert nuevo_b == pytest.approx(1632 + 5 * (1 - (1 - p_a)))
    assert abs(nuevo_a - 1413.79) < 0.1
    assert abs(nuevo_b - 1633.15) < 0.1


def test_ejemplo_del_reglamento_redondeando_p_v():
    """El ejemplo publicado se reproduce exacto si se redondea p_v a 2 decimales.

    Escenario del reglamento (págs. 13–15): ``p_A = 0.23`` y ``p_B = 0.77``.
    ``1420 + 27·(1 − 0.23) = 1440.79`` y ``1632 + 5·(0 − 0.77) = 1628.15``.
    """
    p_a = round(expected_score(1420, 1632), 2)
    p_b = round(1 - expected_score(1420, 1632), 2)
    assert p_a == 0.23 and p_b == 0.77
    assert round(1420 + 27 * (1 - p_a), 2) == 1440.79
    assert round(1632 + 5 * (0 - p_b), 2) == 1628.15
    assert round(1420 + 27 * (0 - p_a), 2) == 1413.79
    assert round(1632 + 5 * (1 - p_b), 2) == 1633.15


def test_k_del_ejemplo_del_reglamento_usa_las_tablas():
    """Las tablas (normativas) difieren del ejemplo ilustrativo del reglamento.

    El ejemplo afirma ``t = 15`` para 25 combates y ``t = 5`` para 64, y
    ``x = 1`` para el tramo 76–84.9 %. Las tablas publicadas dan ``t(25) = 5``,
    ``t(64) = 2.5`` y ``x(80) = 0.5``. Decisión cerrada con el usuario:
    **prevalecen las tablas** y el ejemplo se trata como ilustrativo.
    """
    assert t_factor(25) == 5.0        # ejemplo: 15  → tabla: 21–40 → 5
    assert t_factor(64) == 2.5        # ejemplo: 5   → tabla: 41–60 → 2.5
    assert x_factor(80.0) == 0.5      # ejemplo: 1   → tabla: 76–84.9 → 0.5
    assert k_factor(25, 30.0) == pytest.approx(9.0)     # 5 · 1.8
    assert k_factor(64, 80.0) == pytest.approx(1.25)    # 2.5 · 0.5
