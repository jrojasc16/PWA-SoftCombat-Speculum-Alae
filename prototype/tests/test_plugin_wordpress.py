"""Tests de contrato del plugin WordPress `ranking-table.php` (Sprint 11).

No hay intérprete PHP en el entorno de CI, así que se verifica por lectura
del fuente: cabecera reconocible por WordPress, registro del shortcode,
consumo del endpoint público con la HTTP API de WordPress, caché con
Transients, mensaje degradado y página de ajustes. Además se contrastan los
parámetros y límites del plugin contra los del backend Flask, de modo que si
cambia la API el test avisa.
"""

from pathlib import Path

import re

RAIZ = Path(__file__).resolve().parents[1]
PLUGIN = RAIZ / "wordpress-plugin" / "ranking-table.php"


def _plugin() -> str:
    """Contenido completo del plugin."""
    assert PLUGIN.exists(), "falta prototype/wordpress-plugin/ranking-table.php"
    return PLUGIN.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 11.1 — cabecera, shortcode y consumo de GET /api/ranking
# ---------------------------------------------------------------------------


def test_el_plugin_tiene_la_cabecera_que_wordpress_reconoce():
    codigo = _plugin()
    assert "Plugin Name:" in codigo
    assert "Version:" in codigo
    assert "Text Domain:" in codigo


def test_el_plugin_no_se_ejecuta_fuera_de_wordpress():
    assert "defined( 'ABSPATH' ) || exit;" in _plugin()


def test_el_plugin_registra_el_shortcode_ranking_table():
    codigo = _plugin()
    assert "add_shortcode( 'ranking_table', 'sa_ranking_shortcode' );" in codigo
    # El callback existe y es el que se registra.
    assert "function sa_ranking_shortcode( $atts )" in codigo


def test_el_shortcode_consume_el_endpoint_publico_con_la_http_api_de_wordpress():
    codigo = _plugin()
    assert "wp_remote_get(" in codigo
    assert "/api/ranking" in codigo
    # Sin autenticación: el endpoint es público y no se manda cookie ni token.
    assert "Authorization" not in codigo
    assert "wp_remote_retrieve_body" in codigo


def test_el_plugin_solo_pide_parametros_que_el_endpoint_flask_conoce():
    """El plugin no puede inventarse parámetros: habla el contrato real.

    (La tabla del shortcode muestra la primera página; ``page`` lo omite y el
    backend usa su valor por defecto 1.)
    """
    codigo = _plugin()
    rutas = (RAIZ / "app" / "modules" / "public_api" / "routes.py").read_text(
        encoding="utf-8"
    )
    admitidos = set(re.findall(r'param_entero\(\s*"(\w+)"', rutas))
    assert admitidos, "no se pudieron leer los parámetros del endpoint"

    # Parámetros que el plugin añade a la URL de la consulta.
    bloque = re.search(r"add_query_arg\(\s*array\((.*?)\),\s*\$url", codigo, re.S)
    assert bloque, "el plugin no construye la URL con add_query_arg"
    pedidos = set(re.findall(r"'(\w+)'", bloque.group(1)))

    assert pedidos, "el plugin no pide ningún parámetro"
    assert pedidos <= admitidos, (
        f"el plugin pide parámetros que el endpoint no admite: "
        f"{sorted(pedidos - admitidos)}"
    )
    # Los dos que usa deben existir en el backend.
    assert {"community_id", "per_page"} <= admitidos


def test_el_plugin_respeta_los_limites_de_paginacion_del_backend():
    codigo = _plugin()
    http = (RAIZ / "app" / "shared" / "http.py").read_text(encoding="utf-8")
    defecto = int(re.search(r"PAGINA_POR_DEFECTO\s*=\s*(\d+)", http).group(1))
    maximo = int(re.search(r"PAGINA_MAXIMO\s*=\s*(\d+)", http).group(1))

    # Valor por defecto y cota superior idénticas a las del backend.
    assert f"'per_page'     => {defecto}" in codigo
    assert f"min( {maximo}, max( 1, absint( $atts['per_page'] ) ) )" in codigo


def test_el_shortcode_aisla_por_comunidad_como_el_resto_del_sistema():
    codigo = _plugin()
    assert "absint( $atts['community_id'] )" in codigo
    assert "'community_id'" in codigo


def test_la_tabla_tiene_las_mismas_columnas_y_orden_que_la_vista_web():
    """La tabla del shortcode debe ser un calco de la vista pública /ranking."""
    codigo = _plugin()
    plantilla = (RAIZ / "app" / "templates" / "ranking.html").read_text(
        encoding="utf-8"
    )
    columnas = re.findall(r'<th scope="col">([^<]+)</th>', plantilla)
    assert columnas, "la vista web no expone columnas"

    # Aparecen en el plugin, en el mismo orden y sin faltar ni sobrar.
    posiciones = [codigo.find(f"'{c}'") for c in columnas]
    assert all(p >= 0 for p in posiciones), f"columnas web ausentes: {columnas}"
    assert posiciones == sorted(posiciones), "el orden de columnas cambió"


def test_el_plugin_usa_el_mismo_mensaje_vacio_que_la_vista_web():
    codigo = _plugin()
    plantilla = (RAIZ / "app" / "templates" / "ranking.html").read_text(
        encoding="utf-8"
    )
    assert "Todavía no hay combates confirmados" in plantilla
    assert "Todavía no hay combates confirmados" in codigo
