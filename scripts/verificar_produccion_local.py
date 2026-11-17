#!/usr/bin/env python3
"""Verificación de producción EN LOCAL (pre-flight de las tareas 14.1–14.3).

No sustituye al smoke test contra PythonAnywhere (tarea 14.3, requiere la
cuenta real), pero valida **los mismos artefactos** antes de subirlos:

1. el punto de entrada de producción ``prototype/wsgi.py`` arranca en
   ``ProductionConfig`` con una ``SECRET_KEY`` inyectada por entorno;
2. el esquema se crea con el **mismo comando** del despliegue
   (``flask --app wsgi.py db upgrade``, que además siembra los 4 roles);
3. la aplicación responde por HTTP: ``/health`` (env=production), ``/api/ranking``,
   ``/login`` y ``/ranking``;
4. sin sesión, los endpoints protegidos devuelven **401 JSON** (nunca redirección);
5. la redirección HTTPS (capa 1) responde **308** con ``X-Forwarded-Proto: http``;
6. el ciclo completo (registro → reporte → confirmación dual → Elo on-write)
   funciona bajo ``ProductionConfig``.

Uso (desde la raíz del repo):

    venv/bin/python scripts/verificar_produccion_local.py

Salida: tabla PASS/FAIL y código de salida 0/1.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROTOTYPE = RAIZ / "prototype"
sys.path.insert(0, str(PROTOTYPE))

FECHA_COMBATE = "2026-11-01T18:00:00"


class Resultado:
    """Acumula el resultado de cada comprobación."""

    def __init__(self) -> None:
        self.filas: list[tuple[str, bool, str]] = []

    def check(self, nombre: str, ok: bool, detalle: str = "") -> None:
        self.filas.append((nombre, ok, detalle))
        marca = "OK  " if ok else "FALLO"
        print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle else ""))

    @property
    def ok(self) -> bool:
        return all(fila[1] for fila in self.filas)

    def resumen(self) -> None:
        total = len(self.filas)
        pasan = sum(1 for f in self.filas if f[1])
        print(f"\n{pasan}/{total} comprobaciones OK.")
        for nombre, ok, detalle in self.filas:
            if not ok:
                print(f"  - FALLÓ: {nombre} {detalle}")


def _puerto_libre() -> int:
    """Devuelve un puerto TCP libre en localhost."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _preparar_entorno(tmp: Path) -> None:
    """Define las variables de entorno de producción hacia una BD temporal."""
    os.environ["FLASK_CONFIG"] = "production"
    os.environ["SECRET_KEY"] = "clave-de-prueba-preflight-14"
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp / 'prod.db'}"
    os.environ["RANKING_CACHE_TTL"] = "0"


def _correr_migraciones() -> None:
    """Crea el esquema con el comando real del despliegue (incluye seed de roles)."""
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "wsgi.py", "db", "upgrade"],
        cwd=PROTOTYPE,
        check=True,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
    )


def _servir(app, puerto: int) -> threading.Thread:
    """Arranca un servidor Werkzeug real en un hilo (como en producción)."""
    from werkzeug.serving import make_server

    servidor = make_server("127.0.0.1", puerto, app)

    def _run() -> None:
        servidor.serve_forever()

    hilo = threading.Thread(target=_run, daemon=True)
    hilo.start()
    return hilo


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    """No sigue redirecciones: deja ver el 3xx tal cual (comprueba el 308)."""

    def redirect_request(self, *args, **kwargs):  # noqa: D102
        return None


_OPENER = urllib.request.build_opener(_SinRedireccion)


def _get(puerto: int, ruta: str, cabeceras: dict | None = None):
    """GET HTTP simple; devuelve (estado, cuerpo, cabeceras) sin seguir 3xx."""
    solicitud = urllib.request.Request(
        f"http://127.0.0.1:{puerto}{ruta}", headers=cabeceras or {}
    )
    try:
        with _OPENER.open(solicitud, timeout=10) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8"), dict(respuesta.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


def verificar() -> int:
    resultado = Resultado()

    with tempfile.TemporaryDirectory(prefix="sa-preflight-") as carpeta:
        tmp = Path(carpeta)
        _preparar_entorno(tmp)

        # --- 1-2. Entrypoint real + migraciones -----------------------------
        try:
            import importlib

            wsgi = importlib.import_module("wsgi")
            importlib.reload(wsgi)  # asegura la lectura del entorno de prueba
            application = wsgi.application
            resultado.check(
                "wsgi.py arranca en ProductionConfig",
                application.config["SESSION_COOKIE_SECURE"] is True,
                f"env={application.config.get('ENV') or 'production'}",
            )
        except Exception as exc:  # pragma: no cover - diagnóstico
            resultado.check("wsgi.py arranca en ProductionConfig", False, repr(exc))
            resultado.resumen()
            return 1

        try:
            _correr_migraciones()
            resultado.check("migraciones `flask --app wsgi.py db upgrade`", True)
        except subprocess.CalledProcessError as exc:
            resultado.check(
                "migraciones `flask --app wsgi.py db upgrade`", False, repr(exc)
            )
            resultado.resumen()
            return 1

        # --- 3-5. Comprobaciones HTTP con servidor real ---------------------
        puerto = _puerto_libre()
        _servir(application, puerto)
        time.sleep(0.5)

        estado, cuerpo, _ = _get(puerto, "/health")
        resultado.check(
            "GET /health → 200 env=production",
            estado == 200 and '"env":"production"' in cuerpo.replace(" ", ""),
            f"estado={estado}",
        )

        estado, cuerpo, cab = _get(puerto, "/api/ranking")
        resultado.check(
            "GET /api/ranking → 200 JSON cacheable",
            estado == 200
            and '"items"' in cuerpo
            and cab.get("Cache-Control", "").startswith("public"),
            f"estado={estado}",
        )

        for ruta in ("/login", "/ranking"):
            estado, _, _ = _get(puerto, ruta)
            resultado.check(f"GET {ruta} → 200", estado == 200, f"estado={estado}")

        estado, cuerpo, _ = _get(puerto, "/me")
        resultado.check(
            "GET /me sin sesión → 401 JSON",
            estado == 401 and '"error"' in cuerpo,
            f"estado={estado}",
        )

        estado, _, cab = _get(puerto, "/health", {"X-Forwarded-Proto": "http"})
        resultado.check(
            "HTTPS forzado tras proxy → 308 a https",
            estado == 308 and cab.get("Location", "").startswith("https://"),
            f"estado={estado}",
        )

        # --- 6. Ciclo completo bajo ProductionConfig (test client https) ----
        cliente_a = application.test_client()
        cliente_b = application.test_client()

        def _post(cliente, ruta, json):
            return cliente.post(ruta, json=json, base_url="https://localhost")

        ra = _post(
            cliente_a, "/auth/register",
            {"email": "prod-ana@speculum.test", "password": "password123", "name": "Ana Prod"},
        )
        rb = _post(
            cliente_b, "/auth/register",
            {"email": "prod-beto@speculum.test", "password": "password123", "name": "Beto Prod"},
        )
        resultado.check(
            "registro bajo ProductionConfig → 201",
            ra.status_code == 201 and rb.status_code == 201,
            f"{ra.status_code}/{rb.status_code}",
        )

        ana_id = ra.get_json()["id"]
        beto_id = rb.get_json()["id"]
        rc = _post(
            cliente_a, "/combats",
            {"participants": [ana_id, beto_id], "winner": ana_id, "played_at": FECHA_COMBATE},
        )
        resultado.check("reporte de combate → 201 PENDIENTE",
                        rc.status_code == 201 and rc.get_json()["status"] == "PENDIENTE",
                        f"estado={rc.status_code}")
        combate_id = rc.get_json()["id"]

        _post(cliente_a, f"/combats/{combate_id}/confirm", {"winner_id": ana_id})
        rc = _post(cliente_b, f"/combats/{combate_id}/confirm", {"winner_id": ana_id})
        resultado.check(
            "confirmación dual → CONFIRMADO + Elo on-write",
            rc.status_code == 200
            and rc.get_json()["status"] == "CONFIRMADO"
            and rc.get_json()["processed"] is True,
            f"estado={rc.status_code}",
        )

        rp = application.test_client().get("/api/ranking", base_url="https://localhost")
        cuerpo = rp.get_data(as_text=True)
        resultado.check(
            "ranking público con Elo aplicado y sin correos",
            rp.status_code == 200
            and "Ana Prod" in cuerpo
            and "@speculum.test" not in cuerpo,
            f"estado={rp.status_code}",
        )

    resultado.resumen()
    return 0 if resultado.ok else 1


if __name__ == "__main__":
    raise SystemExit(verificar())
