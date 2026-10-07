"""Núcleo Elo PURO (sin Flask ni SQLAlchemy): constante k por n.º de combates y percentil, fórmula del reglamento (págs. 13-15).

Implementa el Art. 30 del reglamento nacional de SoftCombat 2021:

- ``p_v = 1 / (1 + 10 ** ((índice_oponente - Índice_propio) / 400))``
- ``ΔI = Índice + k · (r − p_v)`` con ``r ∈ {1 victoria, 0 derrota}``
- ``k = t · x`` (tablas en ``.constants``)

Restricciones de diseño (plan de desarrollo, tareas 3.2–3.3):

- Funciones puras y tipadas: sin I/O, sin fechas, sin estado, sin dependencias
  externas (ni Flask, ni SQLAlchemy, ni red). Se puede importar el módulo sin
  crear una aplicación Flask; el test ``test_elo_puro_no_importa_framework``
  lo verifica sobre el AST.
- El reglamento **no contempla empates** (solo ``r = 1`` y ``r = 0``), por lo
  que ``Resultado`` expone únicamente victoria de A o de B.
- Precisión: las fórmulas se evalúan con **precisión completa**. El ejemplo de
  las págs. 13–15 redondea ``p_v`` a 2 decimales antes de sustituir (de ahí
  1440.79 frente a 1440.85); se documenta con un test de tolerancia.
"""

from __future__ import annotations

from enum import Enum
import math

from .constants import RATING_INICIAL, TABLA_T, TABLA_X

__all__ = [
    "RATING_INICIAL",
    "Resultado",
    "expected_score",
    "t_factor",
    "x_factor",
    "k_factor",
    "new_ratings",
]

# Constante de escala de la fórmula Elo (Art. 30, págs. 13–15).
_ESCALA_ELO = 400.0


class Resultado(str, Enum):
    """Resultado de un combate de dos jugadores según el reglamento.

    El Art. 30 solo define ``r = 1`` (victoria) y ``r = 0`` (derrota): no
    existe empate en la fórmula, así que el dominio tampoco lo expone.
    """

    VICTORIA_A = "victoria_a"
    VICTORIA_B = "victoria_b"


def _validar_rating(valor: float, nombre: str) -> float:
    """Comprueba que un índice sea un número finito (ValueError en caso contrario)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{nombre} debe ser numérico, recibido: {valor!r}")
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError(f"{nombre} debe ser finito, recibido: {valor!r}")
    return numero


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probabilidad de victoria de A contra B (``p_v`` del Art. 30).

    Args:
        rating_a: índice actual de A.
        rating_b: índice actual de B.

    Returns:
        Valor en ``(0, 1)``. Si ambos índices son iguales devuelve ``0.5``.
    """
    a = _validar_rating(rating_a, "rating_a")
    b = _validar_rating(rating_b, "rating_b")
    return 1.0 / (1.0 + 10.0 ** ((b - a) / _ESCALA_ELO))


def t_factor(combates: int) -> float:
    """Variable ``t`` del reglamento según el número de combates de ranking.

    Args:
        combates: número de combates de ranking del jugador (>= 0).

    Returns:
        Valor de la tabla (10, 7.5, 5, 2.5 o 0.5).

    Raises:
        ValueError: si ``combates`` no es un entero no negativo.
    """
    if isinstance(combates, bool) or not isinstance(combates, int):
        raise ValueError(f"combates debe ser un entero, recibido: {combates!r}")
    if combates < 0:
        raise ValueError(f"combates no puede ser negativo, recibido: {combates!r}")
    # TABLA_T está ordenada por límite inferior: se queda el último tramo
    # cuyo límite sea <= combates (el último no tiene tope superior).
    valor_tramo = TABLA_T[0][1]
    for desde, candidato in TABLA_T:
        if combates >= desde:
            valor_tramo = candidato
        else:
            break
    return valor_tramo


def x_factor(percentil: float) -> float:
    """Variable ``x`` del reglamento según el percentil en el ranking.

    El percentil se mide **desde el fondo**: ``0 %`` es el último puesto y
    ``100 %`` la primera posición (la primera posición tiene ``x = 0.2``).

    Args:
        percentil: percentil en ``[0, 100]``.

    Returns:
        Valor de la tabla (2, 1.8, 1.6, 0.7, 0.6, 0.5, 0.4, 0.3 o 0.2).

    Raises:
        ValueError: si ``percentil`` no es finito o cae fuera de ``[0, 100]``.
    """
    valor = _validar_rating(percentil, "percentil")
    if valor < 0.0 or valor > 100.0:
        raise ValueError(f"percentil debe estar en [0, 100], recibido: {percentil!r}")
    x = TABLA_X[0][1]
    for desde, candidato in TABLA_X:
        if valor >= desde:
            x = candidato
        else:
            break
    return x


def k_factor(combates: int, percentil: float) -> float:
    """Constante ``k = t · x`` del reglamento (veteranía × posición).

    Args:
        combates: número de combates de ranking del jugador.
        percentil: percentil del jugador desde el fondo (``[0, 100]``).

    Returns:
        ``t · x`` (> 0 para todos los tramos de las tablas).
    """
    return t_factor(combates) * x_factor(percentil)


def new_ratings(
    rating_a: float,
    rating_b: float,
    resultado: Resultado | str,
    k_a: float,
    k_b: float,
) -> tuple[float, float]:
    """Aplica ``ΔI = Índice + k · (r − p_v)`` a ambos jugadores.

    Args:
        rating_a: índice actual de A.
        rating_b: índice actual de B.
        resultado: ``Resultado.VICTORIA_A`` o ``Resultado.VICTORIA_B``
            (también se acepta su valor string).
        k_a: constante k de A.
        k_b: constante k de B.

    Returns:
        Tupla ``(nuevo_índice_a, nuevo_índice_b)`` sin redondear.

    Raises:
        ValueError: índices no finitos, k negativos o resultado desconocido.
    """
    a = _validar_rating(rating_a, "rating_a")
    b = _validar_rating(rating_b, "rating_b")
    ka = _validar_rating(k_a, "k_a")
    kb = _validar_rating(k_b, "k_b")
    if ka < 0.0 or kb < 0.0:
        raise ValueError(f"Las constantes k deben ser >= 0 (k_a={k_a!r}, k_b={k_b!r}).")

    try:
        victoria = Resultado(resultado)
    except ValueError as exc:
        raise ValueError(
            f"Resultado desconocido: {resultado!r} (se admite "
            f"{Resultado.VICTORIA_A.value!r} o {Resultado.VICTORIA_B.value!r})."
        ) from exc

    esperado_a = expected_score(a, b)
    esperado_b = expected_score(b, a)
    r_a = 1.0 if victoria is Resultado.VICTORIA_A else 0.0
    r_b = 1.0 - r_a
    nuevo_a = a + ka * (r_a - esperado_a)
    nuevo_b = b + kb * (r_b - esperado_b)
    return nuevo_a, nuevo_b
