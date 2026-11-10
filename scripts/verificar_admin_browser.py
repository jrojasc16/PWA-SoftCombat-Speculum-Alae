"""Verificación en un navegador real del panel de administración (Sprint 10).

Ejecuta la prueba «entrar como admin → gestionar usuarios → resolver un
conflicto → ver la bitácora → recalcular el ranking» dentro de un navegador sin
interfaz (Microsoft Edge headless), usando la página de prueba
``scripts/harness_admin.html``.

El script abre el navegador con un puerto de depuración y delega la espera del
resultado en ``scripts/cdp_esperar_resultado.mjs`` (Node), que habla el
protocolo DevTools. Requisitos:

- La aplicación en marcha (por defecto ``http://127.0.0.1:5000``).
- Un navegador Chromium/Edge y Node 18+ (en este entorno: el Edge y el Node de
  Windows). Se pueden indicar con ``--navegador`` y ``--node``.

Antes de abrir el navegador siembra los datos de prueba (un administrador, un
rival y un combate en conflicto) en la base de datos de la aplicación.

Uso:

    venv/bin/python scripts/verificar_admin_browser.py
    venv/bin/python scripts/verificar_admin_browser.py --url http://127.0.0.1:5000

Devuelve 0 si todos los pasos de la prueba pasan y 1 si alguno falla.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
HARNESS = RAIZ_REPO / "scripts" / "harness_admin.html"
ESPERADOR = RAIZ_REPO / "scripts" / "cdp_esperar_resultado.mjs"
ESTATICOS = RAIZ_REPO / "prototype" / "app" / "static"

# Correos de los datos de prueba sembrados.
ADMIN_PRUEBA = "admin@prueba.local"
RIVAL_PRUEBA = "rival@prueba.local"
CONTRINCANTE_PRUEBA = "contrincante@prueba.local"
PASSWORD_PRUEBA = "password123"

NAVEGADORES_WINDOWS = [
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
]

NODES_WINDOWS = [
    "/mnt/c/Program Files/nodejs/node.exe",
    "/mnt/c/Program Files (x86)/nodejs/node.exe",
]


def _detectar_navegador() -> str | None:
    """Busca un navegador Chromium instalado en el sistema."""
    for ruta in NAVEGADORES_WINDOWS:
        if Path(ruta).exists():
            return ruta
    for nombre in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        encontrado = shutil.which(nombre)
        if encontrado:
            return encontrado
    return None


def _detectar_node() -> str | None:
    """Busca el intérprete de Node (necesario para hablar el protocolo DevTools)."""
    for ruta in NODES_WINDOWS:
        if Path(ruta).exists():
            return ruta
    return shutil.which("node")


def _perfil_temporal() -> str:
    """Directorio de perfil desechable (accesible desde Windows si es posible)."""
    base = Path("/mnt/c/Temp") if Path("/mnt/c/Temp").exists() else Path("/tmp")
    return str(base / f"perfil-navegador-{int(time.time())}")


def _ruta_windows(ruta: str) -> str:
    """Convierte una ruta de WSL en su equivalente de Windows (para el navegador).

    ``/mnt/e/proyecto/scripts/x.mjs`` → ``E:\\proyecto\\scripts\\x.mjs``.
    """
    if not ruta.startswith("/mnt/"):
        return ruta
    partes = ruta.lstrip("/").split("/", 2)
    if len(partes) < 3:
        return ruta
    letra = partes[1]
    resto = partes[2] if len(partes) > 2 else ""
    return letra.upper() + ":\\" + resto.replace("/", "\\")


def _puerto_libre() -> int:
    """Reserva un puerto local libre para el puerto de depuración."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sembrar_datos() -> None:
    """Siembra el administrador, el rival y un combate en conflicto.

    Es idempotente: si los datos ya existen, no se duplican.
    """
    sys.path.insert(0, str(RAIZ_REPO / "prototype"))

    from app import create_app
    from app.extensions import db
    from app.modules.combat import services as combat_services
    from app.modules.iam import services as iam_services
    from app.modules.iam.models import Role
    from app.modules.iam.repositories import RoleRepository, UserRepository

    app = create_app()
    with app.app_context():
        db.create_all()
        for nombre in ("jugador", "arbitro", "admin", "super_admin"):
            if RoleRepository.get_by_name(nombre) is None:
                db.session.add(Role(name=nombre))
        db.session.commit()

        def usuario(email: str, nombre: str, rol: str):
            existente = UserRepository.get_by_email(email)
            if existente is not None:
                return existente
            creado = iam_services.register_user(
                email=email, password=PASSWORD_PRUEBA, name=nombre, community_id=1
            )
            creado.role_id = RoleRepository.get_by_name(rol).id
            db.session.commit()
            return creado

        admin = usuario(ADMIN_PRUEBA, "Admin de Prueba", "admin")
        rival = usuario(RIVAL_PRUEBA, "Rival de Prueba", "jugador")
        contrincante = usuario(CONTRINCANTE_PRUEBA, "Contrincante de Prueba", "jugador")

        # Combate en conflicto: las dos confirmaciones discrepan.
        jugada = datetime.now() - timedelta(days=1)
        combate, _ = combat_services.report_combat(
            reporter_id=rival.id,
            participants=[rival.id, contrincante.id],
            winner=rival.id,
            played_at=jugada,
        )
        combat_services.confirm_combat(
            user_id=rival.id, combat_id=combate.id, result={"winner_id": rival.id}
        )
        combat_services.confirm_combat(
            user_id=contrincante.id,
            combat_id=combate.id,
            result={"winner_id": contrincante.id},
        )
        db.session.commit()
        if combate.status.value != "CONFLICTO":
            raise RuntimeError("La semilla no dejó el combate en CONFLICTO.")
        print(
            f"Datos sembrados: admin={admin.id}, combate en conflicto={combate.id}."
        )


def ejecutar_prueba(url_base: str, navegador: str, node: str, timeout: int = 240):
    """Ejecuta la página de prueba en el navegador y devuelve los pasos."""
    if not HARNESS.exists():
        raise FileNotFoundError(f"No se encuentra la página de prueba: {HARNESS}")
    if not ESPERADOR.exists():
        raise FileNotFoundError(f"No se encuentra el esperador CDP: {ESPERADOR}")

    destino = ESTATICOS / "harness-prueba-admin.html"
    shutil.copyfile(HARNESS, destino)

    puerto = _puerto_libre()
    perfil = _perfil_temporal()
    url_prueba = url_base.rstrip("/") + "/static/harness-prueba-admin.html"
    comando = [
        navegador,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--disable-extensions",
        f"--user-data-dir={_ruta_windows(perfil)}",
        f"--remote-debugging-port={puerto}",
        "about:blank",
    ]

    proceso = subprocess.Popen(
        comando,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        resultado = subprocess.run(
            [
                node,
                _ruta_windows(str(ESPERADOR)),
                "--port",
                str(puerto),
                "--url",
                url_prueba,
                "--selector",
                "#resultado",
                "--timeout-ms",
                "90000",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if resultado.returncode != 0:
            raise RuntimeError(
                "La página de prueba no devolvió un resultado válido.\n"
                f"Salida: {resultado.stdout[:500]}\nErrores: {resultado.stderr[:500]}"
            )
        try:
            valor = json.loads(resultado.stdout).get("valor", "")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Salida inesperada del esperador: {resultado.stdout[:500]}"
            ) from exc
        if not valor or valor == "TIMEOUT":
            raise RuntimeError("La prueba en el navegador no terminó a tiempo.")
        return json.loads(valor)
    finally:
        destino.unlink(missing_ok=True)
        shutil.rmtree(perfil, ignore_errors=True)
        proceso.terminate()
        try:
            proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proceso.kill()


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--url", default="http://127.0.0.1:5000")
    analizador.add_argument("--navegador", default=None)
    analizador.add_argument("--node", default=None)
    analizador.add_argument(
        "--sin-sembrar",
        action="store_true",
        help="No siembra los datos de prueba (si ya existen).",
    )
    argumentos = analizador.parse_args()

    navegador = argumentos.navegador or _detectar_navegador()
    node = argumentos.node or _detectar_node()
    if not navegador:
        print(
            "No se encontró un navegador Chromium/Edge. Indícalo con "
            "--navegador /ruta/al/navegador."
        )
        return 1
    if not node:
        print("No se encontró Node (necesario para hablar el protocolo DevTools).")
        return 1

    print(f"Navegador: {navegador}")
    print(f"Node: {node}")
    print(f"Aplicación: {argumentos.url}")

    try:
        if not argumentos.sin_sembrar:
            sembrar_datos()
        pasos = ejecutar_prueba(argumentos.url, navegador, node)
    except Exception as exc:  # noqa: BLE001 - se informa del fallo al usuario
        print(f"[FALLA] la prueba no pudo ejecutarse: {exc}")
        return 1

    fallidos = 0
    for paso in pasos:
        marca = " OK " if paso.get("ok") else "FALLA"
        detalle = f" — {paso.get('detalle', '')}" if paso.get("detalle") else ""
        print(f"[{marca}] {paso.get('nombre', '')}{detalle}")
        if not paso.get("ok"):
            fallidos += 1

    if fallidos:
        print(f"\nPasos fallidos: {fallidos}")
        return 1
    print("\nEl panel de administración resuelve conflictos y recalcula el ranking.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
