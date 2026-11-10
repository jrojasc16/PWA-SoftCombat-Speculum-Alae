"""Genera los iconos PNG de la PWA (Sprint 8.1) sin dependencias externas.

El proyecto no incluye Pillow/ImageMagick, así que el icono se dibuja píxel a
píxel con supersampling y se codifica un PNG RGBA válido usando solo la
biblioteca estándar (``zlib`` + ``struct``).

Diseño: un rombo dorado (el «espejo» de Speculum-Alae) con centro violeta y
una joya dorada, sobre fondo violeta oscuro. El contenido queda dentro de la
zona segura (10 %–90 %) para que el mismo archivo valga como icono ``any`` y
``maskable``.

Uso (desde la raíz del repo):

    venv/bin/python scripts/generar_iconos_pwa.py

Genera ``prototype/app/static/icons/icon-192.png`` y ``icon-512.png``.
"""

from __future__ import annotations

from pathlib import Path
import struct
import zlib

# Paleta de la PWA (alineada con estilos.css, decisión del Sprint 8).
FONDO = (0x55, 0x0A, 0x56)  # violeta oscuro (--color-acento-oscuro)
ORO = (0xE1, 0xCE, 0x00)  # dorado (--color-borde)
ACENTO = (0x8D, 0x2F, 0x8F)  # violeta (--color-acento)

# Radios normalizados (fracción del lado) de los tres rombos concéntricos.
RADIO_EXTERNO = 0.32
RADIO_INTERNO = 0.20
RADIO_JOYA = 0.08

DESTINO = Path(__file__).resolve().parent.parent / "prototype" / "app" / "static" / "icons"


def _en_rombo(x: float, y: float, radio: float) -> bool:
    """Indica si el punto normalizado cae dentro del rombo centrado."""
    return abs(x - 0.5) + abs(y - 0.5) <= radio


def _color_subpixel(x: float, y: float) -> tuple[int, int, int]:
    """Color del punto: joya dorada, centro violeta, marco dorado o fondo."""
    if _en_rombo(x, y, RADIO_JOYA):
        return ORO
    if _en_rombo(x, y, RADIO_INTERNO):
        return ACENTO
    if _en_rombo(x, y, RADIO_EXTERNO):
        return ORO
    return FONDO


def renderizar(tamano: int, supersampling: int = 4) -> list[bytes]:
    """Renderiza el icono como filas RGBA (con antialiasing por supersampling)."""
    muestras = supersampling * supersampling
    filas: list[bytes] = []
    for py in range(tamano):
        fila = bytearray()
        for px in range(tamano):
            r = g = b = 0
            for sy in range(supersampling):
                y = (py + (sy + 0.5) / supersampling) / tamano
                for sx in range(supersampling):
                    x = (px + (sx + 0.5) / supersampling) / tamano
                    cr, cg, cb = _color_subpixel(x, y)
                    r += cr
                    g += cg
                    b += cb
            fila += bytes((r // muestras, g // muestras, b // muestras, 255))
        filas.append(bytes(fila))
    return filas


def _chunk(tipo: bytes, datos: bytes) -> bytes:
    """Bloque PNG con su longitud y CRC (especificación PNG)."""
    return (
        struct.pack(">I", len(datos))
        + tipo
        + datos
        + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
    )


def escribir_png(ruta: Path, tamano: int, filas: list[bytes]) -> None:
    """Escribe un PNG RGBA (filtro 0 por fila) de forma reproducible."""
    crudo = b"".join(b"\x00" + fila for fila in filas)
    ihdr = struct.pack(">IIBBBBB", tamano, tamano, 8, 6, 0, 0, 0)
    datos = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(crudo, 9))
        + _chunk(b"IEND", b"")
    )
    ruta.write_bytes(datos)


def main() -> None:
    """Genera los dos iconos requeridos por el manifest (192 y 512)."""
    DESTINO.mkdir(parents=True, exist_ok=True)
    for tamano in (192, 512):
        ruta = DESTINO / f"icon-{tamano}.png"
        escribir_png(ruta, tamano, renderizar(tamano))
        print(f"Generado {ruta} ({tamano}×{tamano})")


if __name__ == "__main__":
    main()
