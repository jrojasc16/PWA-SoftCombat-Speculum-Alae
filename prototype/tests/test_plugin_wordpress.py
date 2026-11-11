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


# ---------------------------------------------------------------------------
# 11.2 — caché con Transients (TTL ~5 min) y mensaje degradado
# ---------------------------------------------------------------------------


def test_el_plugin_cachea_el_html_con_transients_de_wordpress():
    codigo = _plugin()
    assert "get_transient(" in codigo
    assert "set_transient(" in codigo
    # Dos transients: el vigente (con TTL) y el respaldo (sin caducidad).
    assert "SA_RANKING_TRANSIENTE" in codigo
    assert "SA_RANKING_TRANSIENTE_RESPALDO" in codigo


def test_el_ttl_por_defecto_es_aproximadamente_5_minutos():
    codigo = _plugin()
    ttl = int(re.search(r"SA_RANKING_TTL_DEFECTO',\s*(\d+)", codigo).group(1))
    assert ttl == 300, "el TTL debe ser ~5 minutos (300 s)"


def test_el_cacheo_es_por_combinacion_de_comunidad_y_pagina():
    """Cada shortcode con atributos distintos tiene su propia entrada."""
    codigo = _plugin()
    assert "function sa_ranking_clave( $comunidad, $por_pagina )" in codigo
    assert "return $comunidad . 'x' . $por_pagina;" in codigo
    # El respaldo sin caducidad usa TTL 0 (semántica de WordPress).
    assert "set_transient( SA_RANKING_TRANSIENTE_RESPALDO, $respaldo, 0 );" in codigo


def test_el_shortcode_sirve_la_cache_antes_de_consultar_el_backend():
    """Orden del flujo: caché → API → respaldo → mensaje degradado."""
    codigo = _plugin()
    cuerpo = re.search(
        r"function sa_ranking_shortcode\(.*?\n}", codigo, re.S
    ).group(0)

    pasos = [
        cuerpo.find("sa_ranking_leer_cache"),
        cuerpo.find("sa_ranking_consultar_api"),
        cuerpo.find("sa_ranking_leer_respaldo"),
        cuerpo.find("sa-ranking-agotado"),
    ]
    assert all(p >= 0 for p in pasos), f"pasos del flujo ausentes: {pasos}"
    assert pasos == sorted(pasos), "el flujo del shortcode cambió de orden"


def test_si_el_backend_no_responde_usa_el_respaldo_y_lo_marca():
    codigo = _plugin()
    assert "is_wp_error( $respuesta )" in codigo
    assert "No se pudo actualizar el ranking: se muestra la última copia guardada." in codigo


def test_sin_respaldo_devuelve_un_mensaje_degradado_legible():
    codigo = _plugin()
    assert "El ranking no está disponible en este momento" in codigo
    assert 'role="status"' in codigo


def test_el_plugin_pone_tope_a_la_espera_de_la_peticion():
    """Un backend colgado no puede bloquear la página de WordPress."""
    codigo = _plugin()
    assert "SA_RANKING_TIMEOUT" in codigo
    assert "'timeout'     => SA_RANKING_TIMEOUT" in codigo


def test_hay_una_funcion_para_vaciar_la_caché():
    codigo = _plugin()
    assert "function sa_ranking_limpiar_cache()" in codigo
    assert "delete_transient( SA_RANKING_TRANSIENTE );" in codigo
    assert "delete_transient( SA_RANKING_TRANSIENTE_RESPALDO );" in codigo
