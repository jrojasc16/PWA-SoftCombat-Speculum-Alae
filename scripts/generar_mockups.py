#!/usr/bin/env python3
"""Captura los mockups HTML de las figuras 10–18 del documento .docx (Sprint 13.4).

Los mockups son páginas estáticas en ``documentation/mockups/figXX-*.html``
(mismo CSS que la PWA) que se abren con ``file://`` en Microsoft Edge headless;
no hace falta servidor ni base de datos. La captura usa el mismo capturador CDP
del manual de usuario (``scripts/cdp_capturar.mjs``).

Requisitos: un navegador Chromium/Edge y Node 18+ (en este entorno: el Edge y
el Node de Windows, igual que en ``capturar_manual_usuario.py``).

Uso (desde la raíz del repo):

    venv/bin/python scripts/generar_mockups.py
    venv/bin/python scripts/generar_mockups.py --navegador ... --node ...

Los PNG resultantes se insertan en el .docx (tarea 13.4).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verificar_admin_browser import (  # noqa: E402  (tras ajustar sys.path)
    _detectar_navegador,
    _detectar_node,
    _perfil_temporal,
    _puerto_libre,
    _ruta_windows,
)

MOCKUPS = RAIZ / "documentation" / "mockups"
MJS = SCRIPTS / "cdp_capturar.mjs"
PLAN_TEMPORAL = MOCKUPS / "_plan.json"

# HTML fuente (uno por figura del .docx) y su PNG de salida.
FIGURAS = (
    "fig10-inicio-sesion",
    "fig11-registro",
    "fig12-inicio-usuario",
    "fig13-ranking-propio",
    "fig14-perfil-publico",
    "fig15-reporte-arbitro",
    "fig16-confirmacion",
    "fig17-reporte-jugador",
    "fig18-login-admin",
)


def construir_plan() -> list[dict]:
    """Pasos de captura (9 PNG) a partir de los HTML en MOCKUPS."""
    plan = []
    for indice, figura in enumerate(FIGURAS, start=10):
        html = MOCKUPS / f"{figura}.html"
        if not html.exists():
            raise FileNotFoundError(f"Falta el mockup: {html.relative_to(RAIZ)}")
        url = "file:///" + _ruta_windows(str(html)).replace("\\", "/")
        plan.append(
            {
                "nombre": figura,
                "url": url,
                "esperar": ".pie",
                "captura": f"{figura}.png",
            }
        )
    return plan


def capturar(navegador: str, node: str, timeout: int) -> list[str]:
    """Ejecuta Edge headless + el capturador CDP y devuelve los PNG obtenidos."""
    if not MJS.exists():
        raise FileNotFoundError(f"No se encuentra el capturador CDP: {MJS}")

    plan = construir_plan()
    PLAN_TEMPORAL.write_text(json.dumps(plan, ensure_ascii=True), encoding="utf-8")

    puerto = _puerto_libre()
    perfil = _perfil_temporal()
    proceso = subprocess.Popen(
        [
            navegador,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
            "--disable-extensions",
            "--hide-scrollbars",
            "--window-size=1280,900",
            f"--user-data-dir={_ruta_windows(perfil)}",
            f"--remote-debugging-port={puerto}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        resultado = subprocess.run(
            [
                node,
                _ruta_windows(str(MJS)),
                "--port",
                str(puerto),
                "--plan",
                _ruta_windows(str(PLAN_TEMPORAL)),
                "--salida",
                _ruta_windows(str(MOCKUPS)),
                "--timeout-ms",
                "25000",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        salida = (resultado.stdout or "").strip().splitlines()
        ultimo = salida[-1] if salida else ""
        try:
            datos = json.loads(ultimo)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Salida inesperada del capturador CDP.\n"
                f"stdout: {resultado.stdout[:600]}\nstderr: {resultado.stderr[:600]}"
            ) from exc
        if resultado.returncode != 0 or "error" in datos:
            raise RuntimeError(
                f"Falló la captura: {datos.get('error', 'error desconocido')}\n"
                f"stderr: {resultado.stderr[:600]}"
            )
        return list(datos.get("capturas", []))
    finally:
        PLAN_TEMPORAL.unlink(missing_ok=True)
        proceso.terminate()
        try:
            proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proceso.kill()
        shutil.rmtree(perfil, ignore_errors=True)


def verificar(capturados: list[str]) -> None:
    """Comprueba que los 9 PNG existan en disco y no estén vacíos."""
    fallas = []
    for figura in FIGURAS:
        nombre = f"{figura}.png"
        archivo = MOCKUPS / nombre
        if nombre not in capturados:
            fallas.append(f"{nombre}: no lo reportó el navegador")
        elif not archivo.exists() or archivo.stat().st_size < 2000:
            fallas.append(f"{nombre}: archivo ausente o sospechosamente pequeño")
        else:
            print(f"  {nombre}  ({archivo.stat().st_size // 1024} KiB)")
    if fallas:
        raise RuntimeError("Capturas incompletas:\n  " + "\n  ".join(fallas))


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--navegador", default=None)
    analizador.add_argument("--node", default=None)
    analizador.add_argument("--timeout", type=int, default=180)
    argumentos = analizador.parse_args()

    navegador = argumentos.navegador or _detectar_navegador()
    if not navegador:
        print(
            "No se encontró un navegador Chromium/Edge. Indícalo con "
            "--navegador /ruta/al/navegador.",
            file=sys.stderr,
        )
        return 1
    node = argumentos.node or _detectar_node()
    if not node:
        print("No se encontró Node. Indícalo con --node /ruta/al/node.", file=sys.stderr)
        return 1

    print(f"Navegador: {navegador}")
    print(f"Node: {node}")

    capturados = capturar(navegador, node, argumentos.timeout)
    verificar(capturados)

    print(f"Listo: {len(capturados)} mockups en {MOCKUPS.relative_to(RAIZ)}/")
    print("Se insertan en el .docx en la tarea 13.4 (scripts/insertar_figuras_docx.py).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — punto único de fallo del script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
