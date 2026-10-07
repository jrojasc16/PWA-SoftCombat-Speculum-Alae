"""Tests del núcleo Elo puro (Sprint 3.4).

Verifican las tablas del Art. 30 (págs. 13–15), la fórmula de probabilidades
y las propiedades exigidas por el plan de desarrollo: simetría, invariancia de
puntos totales con k idénticos y monotonía (ganar nunca baja el índice).

Los casos calculados a mano desde el reglamento viven en ``test_elo_ejemplos``
(3.5) y la pureza/integración del módulo en ``test_elo_integracion`` (3.3).
"""

from __future__ import annotations

import pytest

from app.modules.ranking.domain.constants import RATING_INICIAL, TABLA_T, TABLA_X
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


# ---------------------------------------------------------------------------
# Tabla t (veteranía) — bordes de los tramos, págs. 13–15
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "combates, esperado",
    [
        (0, 10.0),   # "10 o menos"
        (1, 10.0),
        (10, 10.0),  # borde superior del primer tramo
        (11, 7.5),   # "Entre 11 y 20"
        (15, 7.5),
        (20, 7.5),
        (21, 5.0),   # "Entre 21 y 40"
        (30, 5.0),
        (40, 5.0),
        (41, 2.5),   # "Entre 41 y 60"
        (60, 2.5),
        (61, 2.5),   # hueco 61–80 resuelto con 2.5 (decisión documentada)
        (80, 2.5),
        (81, 0.5),   # "Más de 80"
        (500, 0.5),
    ],
)
def test_t_factor_bordes_del_reglamento(combates, esperado):
    """Cada tramo de la tabla t devuelve su valor, incluido el hueco 61–80."""
    assert t_factor(combates) == esperado


def test_tabla_t_coincide_con_el_reglamento():
    """La tabla transcrita respeta exactamente los tramos publicados."""
    assert TABLA_T == ((0, 10.0), (11, 7.5), (21, 5.0), (41, 2.5), (81, 0.5))


@pytest.mark.parametrize("combates", [-1, -100])
def test_t_factor_rechaza_combates_negativos(combates):
    """Un número negativo de combates no tiene tramo: ValueError."""
    with pytest.raises(ValueError, match="negativo"):
        t_factor(combates)


@pytest.mark.parametrize("combates", [1.5, "10", None, True])
def test_t_factor_rechaza_tipos_no_enteros(combates):
    """Solo se aceptan enteros (los bool no cuentan como número de combates)."""
    with pytest.raises(ValueError, match="entero"):
        t_factor(combates)


# ---------------------------------------------------------------------------
# Tabla x (posición en el ranking) — bordes de los tramos, págs. 13–15
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "percentil, esperado",
    [
        (0.0, 2.0),      # fondo exacto → "20 % inferior"
        (10.0, 2.0),
        (19.999, 2.0),
        (20.0, 1.8),     # "Entre el 20 y el 36.9 %"
        (36.9, 1.8),
        (36.999, 1.8),
        (37.0, 1.6),     # "Entre 37 y 51.9 %"
        (51.9, 1.6),
        (52.0, 0.7),     # "Entre 52 y 64.9 %"
        (64.9, 0.7),
        (65.0, 0.6),     # "Entre 65 y 75.9 %"
        (75.9, 0.6),
        (76.0, 0.5),     # "Entre 76 y 84.9 %"
        (84.9, 0.5),
        (85.0, 0.4),     # "Entre 85 y 91.9 %"
        (91.9, 0.4),
        (92.0, 0.3),     # "Entre 92 y 99.9 %"
        (99.9, 0.3),
        (100.0, 0.2),    # "Primera posición del ranking"
    ],
)
def test_x_factor_bordes_del_reglamento(percentil, esperado):
    """Cada tramo de la tabla x devuelve su valor; 100 % es primera posición."""
    assert x_factor(percentil) == esperado


def test_tabla_x_coincide_con_el_reglamento():
    """Los nueve tramos de x se transcriben sin alterar valores ni límites."""
    assert TABLA_X == (
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


@pytest.mark.parametrize("percentil", [-0.1, 100.1, 250.0])
def test_x_factor_rechaza_percentil_fuera_de_rango(percentil):
    """El percentil debe estar en [0, 100]."""
    with pytest.raises(ValueError, match="\\[0, 100\\]"):
        x_factor(percentil)


@pytest.mark.parametrize("percentil", [float("nan"), float("inf"), "50", None, True])
def test_x_factor_rechaza_percentil_no_numerico(percentil):
    """Percentiles no finitos o no numéricos → ValueError."""
    with pytest.raises(ValueError):
        x_factor(percentil)


# ---------------------------------------------------------------------------
# k = t · x
# ---------------------------------------------------------------------------


def test_k_factor_es_producto_de_t_y_x():
    """k = t · x (Art. 30): 40 combates en 76 % → 5 · 0.5 = 2.5."""
    assert k_factor(40, 76.0) == 2.5
    assert k_factor(0, 100.0) == pytest.approx(10.0 * 0.2)
    assert k_factor(1000, 0.0) == pytest.approx(0.5 * 2.0)


def test_k_factor_es_positivo_en_todo_el_dominio():
    """Ningún tramo combinado anula k (evitaría cualquier variación)."""
    for combates in (0, 10, 11, 25, 64, 80, 81, 999):
        for percentil in (0.0, 20.0, 50.0, 80.0, 99.0, 100.0):
            assert k_factor(combates, percentil) > 0.0


# ---------------------------------------------------------------------------
# Probabilidad esperada p_v
# ---------------------------------------------------------------------------


def test_expected_score_indices_iguales_es_05():
    """Dos jugadores con el mismo índice tienen la misma probabilidad."""
    assert expected_score(1500, 1500) == pytest.approx(0.5)


def test_expected_score_es_simetrica():
    """p_A + p_B = 1 para cualquier par de índices (complementariedad)."""
    pares = [(1420, 1632), (1500, 1500), (2000, 800), (0, 3000), (1234.5, 1765.5)]
    for a, b in pares:
        assert expected_score(a, b) + expected_score(b, a) == pytest.approx(1.0)


def test_expected_score_es_monotona():
    """A mayor índice propio, mayor probabilidad de victoria (siempre < 1)."""
    anterior = -1.0
    for rating_propio in (1000, 1300, 1500, 1700, 2000, 2600):
        p = expected_score(rating_propio, 1500)
        assert anterior < p < 1.0
        anterior = p


@pytest.mark.parametrize("valores", [("x", 1500), (1500, None), (True, 1500)])
def test_expected_score_rechaza_indices_no_numericos(valores):
    """Índices no numéricos → ValueError."""
    with pytest.raises(ValueError):
        expected_score(*valores)


def test_expected_score_rechaza_indices_no_finitos():
    """Índices con nan/inf no son válidos (romperían la fórmula)."""
    for malo in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="finito"):
            expected_score(malo, 1500)


# ---------------------------------------------------------------------------
# Nuevos índices: ΔI = Índice + k (r − p_v)
# ---------------------------------------------------------------------------


def test_new_ratings_victoria_del_favorito():
    """El favorito gana poco (p alto → r − p pequeño); el débil pierde poco."""
    nuevo_a, nuevo_b = new_ratings(1800, 1200, VICTORIA_A, k_a=16.0, k_b=16.0)
    assert nuevo_a > 1800
    assert nuevo_b < 1200
    assert nuevo_a - 1800 == pytest.approx(16.0 * (1 - expected_score(1800, 1200)))
    assert 1200 - nuevo_b == pytest.approx(16.0 * expected_score(1200, 1800))


def test_new_ratings_suma_cero_con_k_iguales():
    """Sistema cerrado con k idéntico: los puntos que gana uno los pierde el otro."""
    for a, b in [(1500, 1500), (1420, 1632), (900, 2100), (1750, 1750)]:
        for resultado in (VICTORIA_A, VICTORIA_B):
            nuevo_a, nuevo_b = new_ratings(a, b, resultado, 16.0, 16.0)
            assert (nuevo_a + nuevo_b) == pytest.approx(a + b)


def test_new_ratings_ganar_nunca_baja_el_indice():
    """Monotonía: con k > 0 y p < 1, ganar siempre suma y perder siempre resta."""
    for rating in (800, 1500, 2500):
        for k in (0.1, 5.0, 20.0, 45.0):
            ganador, perdedor = new_ratings(rating, rating, VICTORIA_A, k, k)
            assert ganador > rating
            assert perdedor < rating


def test_new_ratings_es_simetrica_al_intercambiar_papeles():
    """Ganar de A↔B refleja los mismos deltas con los mismos k."""
    a, b, ka, kb = 1420.0, 1632.0, 9.0, 1.25
    nuevo_a, nuevo_b = new_ratings(a, b, VICTORIA_A, ka, kb)
    reflejo_a, reflejo_b = new_ratings(b, a, VICTORIA_B, kb, ka)
    assert reflejo_b == pytest.approx(nuevo_a)
    assert reflejo_a == pytest.approx(nuevo_b)


def test_new_ratings_acepta_el_valor_string_del_resultado():
    """El resultado también se puede pasar como string (serialización JSON)."""
    assert new_ratings(1500, 1500, "victoria_a", 16.0, 16.0) == new_ratings(
        1500, 1500, VICTORIA_A, 16.0, 16.0
    )


def test_new_ratings_rechaza_resultado_desconocido():
    """El reglamento no contempla empates: cualquier otro valor es inválido."""
    for invalido in ("empate", "victoria_c", "", None, 1, 0.5):
        with pytest.raises(ValueError, match="Resultado desconocido"):
            new_ratings(1500, 1500, invalido, 16.0, 16.0)


@pytest.mark.parametrize("k_negativo", [(-1.0, 16.0), (16.0, -0.5)])
def test_new_ratings_rechaza_k_negativos(k_negativo):
    """k no puede ser negativo (invertiría el sentido de la variación)."""
    with pytest.raises(ValueError, match=">= 0"):
        new_ratings(1500, 1500, VICTORIA_A, *k_negativo)


def test_rating_inicial_es_1500():
    """Art. 30: al ingresar al ranking se asigna un índice de 1500."""
    assert RATING_INICIAL == 1500.0
