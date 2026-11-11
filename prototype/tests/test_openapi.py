"""Validación de `docs/openapi.yaml` (Sprint 12.2, RNF007).

Hay dos niveles de comprobación:

1. **Validación del documento** con el validador oficial de OpenAPI
   (``openapi-spec-validator``), que lo contrasta contra el esquema meta de
   OpenAPI 3.0.
2. **Cross-check contra el código real**: que cada ruta documentada exista en
   el mapa de rutas de Flask, que toda ruta JSON de la app esté documentada y
   que los enums y límites del spec coincidan con el dominio y con
   ``shared/http.py``. Así el documento no puede quedarse desfasado sin que un
   test avise.
"""

import re
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

from app.modules.combat.domain.estados import EstadoCombate, ResultadoParticipante
from app.modules.iam.services import ROLES_ADMIN, ROLES_ARBITRO
from app.shared.http import PAGINA_MAXIMO, PAGINA_POR_DEFECTO

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / "docs" / "openapi.yaml"

# Rutas que responden HTML (blueprint ui) o estáticos: no son parte de la API.
_NO_ES_API = ("ui.", "static")


@pytest.fixture(scope="module")
def spec() -> dict:
    """Especificación OpenAPI leída una sola vez para todo el módulo."""
    assert SPEC.exists(), "falta prototype/docs/openapi.yaml"
    documento, _ = read_from_filename(str(SPEC))
    return documento


def _operaciones(documento: dict) -> list[tuple[str, str, dict]]:
    """Lista (ruta, método, operación) de todo el documento."""
    metodos = {"get", "post", "patch", "put", "delete"}
    return [
        (ruta, metodo, operacion)
        for ruta, item in documento["paths"].items()
        for metodo, operacion in item.items()
        if metodo in metodos
    ]


def _ruta_flask(ruta: str) -> str:
    """Convierte la notación OpenAPI ``/a/{id}`` en la de Flask ``/a/<int:id>``."""
    return re.sub(r"\{(\w+)\}", r"<int:\1>", ruta)


# ---------------------------------------------------------------------------
# 1. El documento es OpenAPI válido
# ---------------------------------------------------------------------------


def test_el_spec_es_valido_segun_el_esquema_meta_de_openapi(spec):
    validate(spec)  # lanza ValidationError si el documento no cumple OpenAPI 3.0


def test_el_spec_declara_openapi_3_con_info_completa(spec):
    assert spec["openapi"].startswith("3.")
    info = spec["info"]
    assert info["title"] and info["version"]
    assert info["description"], "falta la descripción general de la API"
    assert info["license"]["name"]


def test_toda_operacion_tiene_operation_id_unico_y_respuestas(spec):
    vistos = set()
    for ruta, metodo, operacion in _operaciones(spec):
        identificador = operacion.get("operationId")
        assert identificador, f"operación sin operationId: {metodo} {ruta}"
        assert identificador not in vistos, f"operationId duplicado: {identificador}"
        vistos.add(identificador)
        assert operacion.get("responses"), f"sin respuestas: {metodo} {ruta}"
        assert operacion.get("summary"), f"sin summary: {metodo} {ruta}"


def test_todas_las_referencias_internas_se_resuelven(spec):
    """Todo ``$ref`` apunta a un componente que existe en el documento."""
    referencias = set(re.findall(r"\$ref:\s*\"([^\"]+)\"", Path(SPEC).read_text("utf-8")))
    assert referencias, "el spec no usa referencias internas"
    for referencia in referencias:
        assert referencia.startswith("#/"), f"referencia externa no soportada: {referencia}"
        actual = spec
        for parte in referencia[2:].split("/"):
            assert parte in actual, f"referencia rota: {referencia}"
            actual = actual[parte]


# ---------------------------------------------------------------------------
# 2. El documento coincide con las rutas reales de Flask
# ---------------------------------------------------------------------------


def test_cada_ruta_documentada_existe_en_flask(spec, app):
    """Nada de lo documentado es ficción: cada path+method está en la app."""
    flask_rules = {
        (rule.rule, metodo)
        for rule in app.url_map.iter_rules()
        for metodo in rule.methods
        if metodo not in ("HEAD", "OPTIONS")
    }
    for ruta, metodo, _ in _operaciones(spec):
        assert (_ruta_flask(ruta), metodo.upper()) in flask_rules, (
            f"el spec documenta {metodo.upper()} {ruta} pero Flask no lo sirve"
        )


def test_toda_ruta_json_de_flask_esta_documentada(spec, app):
    """La documentación cubre toda la API (el blueprint ui es HTML, no API)."""
    documentadas = {
        (_ruta_flask(ruta), metodo.upper()) for ruta, metodo, _ in _operaciones(spec)
    }
    pendientes = []
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        if endpoint.startswith(_NO_ES_API):
            continue
        for metodo in rule.methods:
            if metodo in ("HEAD", "OPTIONS"):
                continue
            if (rule.rule, metodo) not in documentadas:
                pendientes.append(f"{metodo} {rule.rule}")
    assert not pendientes, f"rutas de la API sin documentar: {sorted(pendientes)}"


def _parametros_de(spec: dict, ruta: str, operacion: dict) -> list[str]:
    """Nombres de los parámetros de una operación (resolviendo `$ref`)."""
    nombres = []
    for contenedor in (spec["paths"][ruta], operacion):
        for parametro in contenedor.get("parameters", []):
            if "$ref" in parametro:
                clave = parametro["$ref"].rsplit("/", 1)[-1]
                parametro = spec["components"]["parameters"][clave]
            nombres.append(parametro["name"])
    return nombres


def test_las_rutas_con_parametro_los_declaran_en_el_spec(spec):
    """Si la ruta lleva ``{param}``, la operación declara ese parámetro path."""
    for ruta, _, operacion in _operaciones(spec):
        declarados = _parametros_de(spec, ruta, operacion)
        for parametro in re.findall(r"\{(\w+)\}", ruta):
            assert parametro in declarados, (
                f"{ruta} usa {{{parametro}}} sin declararlo: {declarados}"
            )


# ---------------------------------------------------------------------------
# 3. Contratos del dominio: enums, límites y seguridad
# ---------------------------------------------------------------------------


def test_el_enum_de_estados_coincide_con_la_maquina_de_estados(spec):
    documentado = set(spec["components"]["schemas"]["EstadoCombate"]["enum"])
    real = {estado.value for estado in EstadoCombate}
    assert documentado == real


def test_el_enum_de_resultados_coincide_con_el_dominio(spec):
    documentado = set(spec["components"]["schemas"]["ResultadoParticipante"]["enum"])
    real = {resultado.value for resultado in ResultadoParticipante}
    assert documentado == real


def test_el_enum_de_roles_coincide_con_los_roles_fijos(spec):
    documentado = set(spec["components"]["schemas"]["Rol"]["enum"])
    # Los 4 roles fijos del MVP: jugador + los que ya se usan en autorización.
    reales = {"jugador"} | set(ROLES_ADMIN) | set(ROLES_ARBITRO)
    assert documentado == reales


def test_los_limites_de_paginacion_coinciden_con_shared_http(spec):
    """El spec no puede prometer más filas de las que el backend acepta."""
    parametros = spec["components"]["parameters"]

    por_pagina = parametros["PorPagina"]["schema"]
    assert por_pagina["maximum"] == PAGINA_MAXIMO
    assert por_pagina["default"] == PAGINA_POR_DEFECTO
    assert por_pagina["minimum"] == 1

    assert parametros["Pagina"]["schema"]["default"] == 1


def _seguridad_efectiva(spec: dict, operacion: dict) -> list:
    """Seguridad aplicable a una operación (la suya o la global del spec)."""
    return operacion.get("security", spec.get("security", []))


def test_el_spec_declara_la_seguridad_global_por_cookie(spec):
    """Por defecto toda la API exige la cookie de sesión de Flask-Login."""
    assert spec.get("security") == [{"sesionCookie": []}]
    assert spec["components"]["securitySchemes"]["sesionCookie"]["name"] == "session"


def test_los_endpoints_publicos_no_exigen_sesión(spec):
    publicos = {"/health", "/api/ranking", "/auth/register", "/auth/login"}
    for ruta in publicos:
        for _, _, operacion in _operaciones({**spec, "paths": {ruta: spec["paths"][ruta]}}):
            # `security: []` explícito anula la seguridad global.
            assert _seguridad_efectiva(spec, operacion) == [], f"{ruta} debe ser público"


def test_los_endpoints_protegidos_exigen_la_cookie_de_sesión(spec):
    """Los endpoints con sesión heredan (o repiten) la cookie de Flask-Login."""
    publicos = {"/health", "/api/ranking", "/auth/register", "/auth/login"}
    for ruta, _, operacion in _operaciones(spec):
        if ruta in publicos:
            continue
        assert _seguridad_efectiva(spec, operacion) == [{"sesionCookie": []}], (
            f"{ruta} no exige la cookie de sesión"
        )


def test_los_codigos_de_error_del_spec_son_los_del_manejador_global(spec):
    """400/401/403/404/409 son los códigos que puede emitir app/shared/errors.py."""
    from app.shared.errors import DomainError

    subclases = [DomainError]
    pendientes = [DomainError]
    while pendientes:
        clase = pendientes.pop()
        for subclase in DomainError.__subclasses__():
            if subclase not in subclases:
                subclases.append(subclase)
                pendientes.append(subclase)

    codigos_reales = {str(clase.status_code) for clase in subclases}
    codigos_documentados = {
        codigo
        for _, _, operacion in _operaciones(spec)
        for codigo in operacion["responses"]
    }
    assert codigos_reales <= codigos_documentados, (
        f"códigos de error sin documentar: {sorted(codigos_reales - codigos_documentados)}"
    )


def test_las_respuestas_de_error_compartidas_usan_el_esquema_Error(spec):
    compartidas = spec["components"]["responses"]
    esperadas = {"BadRequest", "NoAutenticado", "SinPermisos", "NoEncontrado", "Conflicto"}
    assert esperadas <= set(compartidas)
    for nombre in esperadas:
        referencia = compartidas[nombre]["content"]["application/json"]["schema"]["$ref"]
        assert referencia == "#/components/schemas/Error"


def test_el_esquema_de_combate_exige_los_campos_que_devuelve_la_ruta(spec):
    """El DTO documentado debe incluir los campos que `_combat_json` serializa."""
    ruta_flask = (RAIZ / "app" / "modules" / "combat" / "routes.py").read_text("utf-8")
    proyeccion = re.search(r"def _combat_json.*?\n    return \{(.*?)\n    \}", ruta_flask, re.S)
    # Solo las claves de primer nivel (8 espacios); las del interior de
    # `participants` están más indentadas y no forman parte del DTO.
    campos_flask = set(re.findall(r'\n {8}"(\w+)":', proyeccion.group(1)))
    campos_spec = set(spec["components"]["schemas"]["Combate"]["required"])
    assert campos_flask == campos_spec, (
        f"desajuste DTO: flask={sorted(campos_flask)} spec={sorted(campos_spec)}"
    )
