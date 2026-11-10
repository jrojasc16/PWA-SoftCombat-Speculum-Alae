"""Verificación en un navegador real del envío offline (Sprint 9).

Ejecuta la prueba «reporte sin conexión → encolado → al recuperar la red se
envía **una sola vez**» dentro de un navegador sin interfaz (Microsoft Edge
headless), usando la página de prueba ``scripts/harness_offline.html``.

El script abre el navegador con un puerto de depuración y delega la espera del
resultado en ``scripts/cdp_esperar_resultado.mjs`` (Node), que habla el
protocolo DevTools. Requisitos:

- La aplicación en marcha (por defecto ``http://127.0.0.1:5000``).
- Un navegador Chromium/Edge y Node 18+ (en este entorno: el Edge y el Node de
  Windows). Se pueden indicar con ``--navegador`` y ``--node``.

Uso:

    venv/bin/python scripts/verificar_offline_browser.py
    venv/bin/python scripts/verificar_offline_browser.py --url http://127.0.0.1:5000

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
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
HARNESS = RAIZ_REPO / "scripts" / "harness_offline.html"
ESPERADOR = RAIZ_REPO / "scripts" / "cdp_esperar_resultado.mjs"
ESTATICOS = RAIZ_REPO / "prototype" / "app" / "static"

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
    if len(partes) < 2:
        return ruta
    letra = partes[1]
    resto = partes[2] if len(partes) > 2 else ""
    return letra.upper() + ":\\" + resto.replace("/", "\\")


def _puerto_libre() -> int:
    """Reserva un puerto local libre para el puerto de depuración."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ejecutar_prueba(url_base: str, navegador: str, node: str, timeout: int = 240):
    """Ejecuta la página de prueba en el navegador y devuelve los pasos."""
    if not HARNESS.exists():
        raise FileNotFoundError(f"No se encuentra la página de prueba: {HARNESS}")
    if not ESPERADOR.exists():
        raise FileNotFoundError(f"No se encuentra el esperador CDP: {ESPERADOR}")

    destino = ESTATICOS / "harness-prueba-offline.html"
    shutil.copyfile(HARNESS, destino)

    puerto = _puerto_libre()
    perfil = _perfil_temporal()
    url_prueba = url_base.rstrip("/") + "/static/harness-prueba-offline.html"
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
            raise RuntimeError(f"Salida inesperada del esperador: {resultado.stdout[:500]}") from exc
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
    print("\nLa cola offline envía el reporte una sola vez al recuperar la red.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
