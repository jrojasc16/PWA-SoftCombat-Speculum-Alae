"""Prueba de humo del Sprint 1: verifica la factory y las fixtures de conftest.

Será sustituida/ampliada por las suites de cada módulo a partir del Sprint 2.
"""


def test_health_responde_ok(client):
    """GET /health responde 200 con JSON de estado (fixture client en memoria)."""
    respuesta = client.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"status": "ok", "env": "testing"}


def test_blueprints_registrados(app):
    """Los 5 blueprints del monolito quedan registrados en la factory."""
    assert sorted(b.name for b in app.blueprints.values()) == [
        "combat",
        "history",
        "iam",
        "public_api",
        "ranking",
    ]
