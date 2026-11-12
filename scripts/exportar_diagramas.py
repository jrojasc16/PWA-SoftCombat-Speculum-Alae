#!/usr/bin/env python3
"""Exporta los diagramas PlantUML (.puml) a PNG usando el servidor público.

Tarea 13.4 (Sprint 13): genera los PNG que se insertan en el documento .docx.
Los .puml son la fuente de verdad (ver documentation/diagrams/README.md).

Codificación PlantUML (texto -> deflate en crudo -> base64 url-safe sin '=').

Uso:
    venv/bin/python scripts/exportar_diagramas.py [nombre ...]
"""
from __future__ import annotations

import base64
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIAGRAMAS = RAIZ / "documentation" / "diagrams"
URL_SERVIDOR = "https://www.plantuml.com/plantuml/png/"
# El servidor devuelve 403 sin un User-Agent de navegador.
AGENTE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ALFABETO = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
)
# Alfabeto base64 estándar, para permutarlo al alfabeto de PlantUML.
ESTANDAR = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
# Los PNG reales actuales pesan >= 31 KB; si se añade un diagrama pequeño,
# revisar la imagen manualmente y ajustar este umbral.
MINIMO_BYTES = 30_000


def codificar(texto: str) -> str:
    """Codifica el fuente PlantUML con la codificación pública estándar."""
    comprimido = zlib.compressobj(9, zlib.DEFLATED, -15)
    datos = comprimido.compress(texto.encode("utf-8")) + comprimido.flush()
    bruto = base64.b64encode(datos).decode("ascii").rstrip("=")
    return bruto.translate(str.maketrans(ESTANDAR, ALFABETO))


def exportar(puml: Path) -> Path:
    png = puml.with_suffix(".png")
    texto = puml.read_text(encoding="utf-8")
    url = URL_SERVIDOR + codificar(texto)
    solicitud = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            cuerpo = respuesta.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"{puml.name}: HTTP {exc.code} — error de sintaxis PlantUML; "
            f"abre en un navegador para ver la marca roja:\n  {url}"
        ) from exc
    if not cuerpo.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"{puml.name}: la respuesta no es PNG")
    if len(cuerpo) < MINIMO_BYTES:
        raise RuntimeError(
            f"{puml.name}: PNG sospechosamente pequeño ({len(cuerpo)} bytes) "
            "— posible error de sintaxis"
        )
    png.write_bytes(cuerpo)
    return png


def main() -> int:
    nombres = sys.argv[1:] or sorted(p.stem for p in DIAGRAMAS.glob("*.puml"))
    fallidos = []
    for nombre in nombres:
        puml = DIAGRAMAS / f"{nombre}.puml"
        if not puml.exists():
            print(f"[SKIP] {nombre}: no existe {puml.relative_to(RAIZ)}")
            fallidos.append(nombre)
            continue
        try:
            png = exportar(puml)
            print(f"[OK]   {png.relative_to(RAIZ)} ({png.stat().st_size} bytes)")
        except (RuntimeError, urllib.error.URLError, TimeoutError) as exc:
            print(f"[FALLO] {nombre}: {exc}")
            fallidos.append(nombre)
        time.sleep(1.0)  # cortesía con el servidor público
    if fallidos:
        print(f"\nFallaron: {', '.join(fallidos)}")
        return 1
    print(f"\n{len(nombres)} diagramas exportados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
