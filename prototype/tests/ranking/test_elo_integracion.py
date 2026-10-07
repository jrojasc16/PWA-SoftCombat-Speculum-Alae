"""Tests de pureza e integración del módulo Elo (Sprint 3.3).

Tarea 3.3: el dominio debe ser un módulo **puro** — dataclasses inmutables,
funciones tipadas, sin I/O, sin fechas y sin librerías externas — de modo que
se pueda importar sin crear (ni necesitar) una aplicación Flask.

Para probarlo de verdad, ``_cargar_dominio_como_paquete_independiente`` carga
``domain/constants.py`` y ``domain/elo.py`` como un paquete aislado de ``app``:
cualquier import de Flask/SQLAlchemy/BD haría fallar la carga.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import types

import pytest

from app.modules.ranking.domain.elo import (
    DueloResultado,
    Resultado,
    expected_score,
    k_factor,
    resolver_duelo,
)

DOMINIO = Path(__file__).resolve().parents[2] / "app" / "modules" / "ranking" / "domain"

VICTORIA_A = Resultado.VICTORIA_A

# Imports permitidos en el dominio puro: solo stdlib de uso declarativo.
IMPORTS_PERMITIDOS = {"__future__", "dataclasses", "enum", "math"}


def _cargar_dominio_como_paquete_independiente() -> types.ModuleType:
    """Carga ``domain/elo.py`` como paquete aislado, sin importar ``app``.

    Requiere que ``elo.py`` use solo imports relativos dentro del paquete
    ``domain`` y stdlib: cualquier dependencia de Flask/SQLAlchemy/BD haría
    fallar la carga.
    """
    nombre = "_dominio_elo_puro"
    paquete = types.ModuleType(nombre)
    paquete.__path__ = [str(DOMINIO)]  # type: ignore[attr-defined]
    sys.modules[nombre] = paquete
    try:
        for modulo in ("constants", "elo"):
            ruta = DOMINIO / f"{modulo}.py"
            spec = importlib.util.spec_from_file_location(f"{nombre}.{modulo}", ruta)
            assert spec and spec.loader
            cargado = importlib.util.module_from_spec(spec)
            sys.modules[f"{nombre}.{modulo}"] = cargado
            spec.loader.exec_module(cargado)
        return sys.modules[f"{nombre}.elo"]
    finally:
        for clave in [k for k in sys.modules if k.startswith(nombre)]:
            sys.modules.pop(clave, None)


def test_elo_se_importa_sin_app_flask():
    """El dominio se carga sin crear (ni necesitar) una aplicación Flask."""
    elo_puro = _cargar_dominio_como_paquete_independiente()
    assert elo_puro.expected_score(1500, 1500) == pytest.approx(0.5)
    assert elo_puro.k_factor(0, 0.0) == 20.0
    assert "flask" not in elo_puro.__dict__
    assert "sqlalchemy" not in elo_puro.__dict__


def test_elo_puro_no_importa_frameworks_ni_bd():
    """AST: los únicos imports permitidos en elo.py son stdlib y el paquete domain."""
    for nombre_archivo in ("elo.py", "constants.py"):
        arbol = ast.parse((DOMINIO / nombre_archivo).read_text(encoding="utf-8"))
        raices: set[str] = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                raices.update(alias.name.split(".")[0] for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                raices.add(nodo.module.split(".")[0])
        no_permitidos = raices - IMPORTS_PERMITIDOS
        assert not no_permitidos, (
            f"{nombre_archivo} importa módulos ajenos al dominio puro: {no_permitidos}"
        )


def test_elo_no_usa_tiempo_ni_abre_archivos():
    """Sin I/O ni fechas: el dominio es determinista y reproducible."""
    fuente = "\n".join(
        (DOMINIO / nombre).read_text(encoding="utf-8")
        for nombre in ("elo.py", "constants.py")
    )
    for prohibido in ("open(", "datetime", "time.", "random", "requests", "os.", "pathlib"):
        assert prohibido not in fuente, f"uso prohibido en el dominio: {prohibido}"


# ---------------------------------------------------------------------------
# dataclasses: DueloResultado (tipado estricto, sin estado mutable)
# ---------------------------------------------------------------------------


def test_resolver_duelo_devuelve_los_datos_completos():
    """Combina las tablas y la fórmula en un único objeto inmutable."""
    duelo = resolver_duelo(
        rating_a=1420,
        rating_b=1632,
        combates_a=25,
        percentil_a=30.0,
        combates_b=64,
        percentil_b=80.0,
        resultado=VICTORIA_A,
    )
    assert isinstance(duelo, DueloResultado)
    assert duelo.k_a == k_factor(25, 30.0) == 5.0 * 1.8
    assert duelo.k_b == k_factor(64, 80.0) == 2.5 * 0.5
    assert duelo.esperado_a + duelo.esperado_b == pytest.approx(1.0)
    assert duelo.delta_a == pytest.approx(duelo.nuevo_a - 1420)
    assert duelo.delta_b == pytest.approx(duelo.nuevo_b - 1632)
    assert duelo.nuevo_a > 1420 and duelo.nuevo_b < 1632


def test_resolver_duelo_es_inmutable():
    """Los resultados son dataclasses congeladas (sin estado compartido)."""
    duelo = resolver_duelo(1500, 1500, 0, 0.0, 0, 0.0, VICTORIA_A)
    with pytest.raises(AttributeError):
        duelo.nuevo_a = 0.0


def test_resolver_duelo_propaga_errores_de_dominio():
    """Una entrada inválida en cualquier parámetro aborta antes de calcular."""
    with pytest.raises(ValueError, match="negativo"):
        resolver_duelo(1500, 1500, -1, 0.0, 0, 0.0, VICTORIA_A)
    with pytest.raises(ValueError, match="\\[0, 100\\]"):
        resolver_duelo(1500, 1500, 0, 0.0, 0, 101.0, VICTORIA_A)
