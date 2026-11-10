"""Tests de los criterios de instalabilidad de la PWA (Sprint 8.4).

Levantan la aplicación en un puerto local efímero y ejecutan el verificador
``scripts/verificar_pwa.py`` contra ella: así los criterios de instalabilidad
que se documentan en el informe del sprint 8.4 quedan verificados de forma
automática y reproducible en la CI.
"""

import importlib.util
import json
import socket
import sys
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

RAIZ_REPO = Path(__file__).resolve().parents[2]
RUTA_VERIFICADOR = RAIZ_REPO / "scripts" / "verificar_pwa.py"


def _cargar_verificador():
    """Importa el script de verificación como módulo (está fuera de ``prototype/``)."""
    spec = importlib.util.spec_from_file_location("verificar_pwa", RUTA_VERIFICADOR)
    modulo = importlib.util.module_from_spec(spec)
    # El módulo se registra antes de ejecutarlo: ``dataclasses`` necesita
    # resolver las anotaciones en ``sys.modules``.
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _puerto_libre() -> int:
    """Reserva un puerto efímero libre para el servidor de pruebas."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servidor(app):
    """Servidor HTTP local con la aplicación de pruebas en marcha."""
    puerto = _puerto_libre()
    servidor = make_server("127.0.0.1", puerto, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)


def test_el_verificador_existe_y_es_ejecutable():
    assert RUTA_VERIFICADOR.exists()


def test_la_documentacion_de_pwa_esta_versionada():
    """Los informes del sprint 8 (instalabilidad y pruebas manuales) existen."""
    documentacion = RAIZ_REPO / "documentation"
    assert (documentacion / "PWA_VERIFICACION_INSTALABILIDAD.md").exists()
    assert (documentacion / "PRUEBAS_MANUALES_PWA.md").exists()


def test_la_app_cumple_los_criterios_de_instalabilidad(servidor):
    verificador = _cargar_verificador()
    informe = verificador.verificar(servidor)

    fallidos = [r.nombre for r in informe.fallos]
    assert not fallidos, f"Criterios de instalabilidad fallidos: {fallidos}"


def test_el_verificador_detecta_un_manifest_incompleto(servidor, monkeypatch):
    """El verificador falla si el manifest pierde un campo obligatorio."""
    verificador = _cargar_verificador()
    descarga_original = verificador._descargar

    def descarga_con_manifest_incompleto(url):
        if url.endswith("/static/manifest.json"):
            manifest = {
                "name": "Speculum-Alae Ranking",
                "icons": [],
            }
            cuerpo = json.dumps(manifest).encode("utf-8")
            return 200, cuerpo, {"Content-Type": "application/json"}
        return descarga_original(url)

    monkeypatch.setattr(verificador, "_descargar", descarga_con_manifest_incompleto)
    informe = verificador.verificar(servidor)

    fallidos = [r.nombre for r in informe.fallos]
    assert "Manifest con «short_name»" in fallidos
    assert "Manifest con display standalone" in fallidos
    assert "Manifest con iconos de 192 y 512 px" in fallidos
