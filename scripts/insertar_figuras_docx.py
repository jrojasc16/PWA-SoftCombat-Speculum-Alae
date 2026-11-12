#!/usr/bin/env python3
"""Inserta los PNG exportados en los 18 espacios reservados del .docx v2 (Sprint 13.4).

Los espacios reservados son tablas de una celda con el texto
``[ ESPACIO RESERVADO PARA FIGURA N ]``. El script sustituye ese marcador (y la
nota «Insertar aquí la imagen manualmente») por la imagen correspondiente,
centrada y escalada para caber en el ancho útil de la página.

Las figuras 1–9 son diagramas UML (``documentation/diagrams/*.png``) y las
figuras 10–18 son mockups de la PWA (``documentation/mockups/*.png``).

Uso (desde la raíz del repo):

    venv/bin/python scripts/insertar_figuras_docx.py [--docx RUTA]

Requiere ``python-docx`` (dependencia de herramienta, no de la app)::
    venv/bin/pip install python-docx
"""

from __future__ import annotations

import argparse
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches

RAIZ = Path(__file__).resolve().parent.parent
DOCX_POR_DEFECTO = (
    RAIZ
    / "documentation"
    / "Metodologia_Proyecto_Ingenieria_Software_Speculum_Alae_v2_PWA.docx"
)
DIAGRAMAS = RAIZ / "documentation" / "diagrams"
MOCKUPS = RAIZ / "documentation" / "mockups"

# Ancho útil de la página (carta) menos un margen de seguridad: 6.0 in disponibles.
ANCHO_MAX = Inches(5.8)
ALTO_MAX = Inches(7.5)

# Figura -> ruta del PNG (figuras 1–9 diagramas; 10–18 mockups).
FIGURAS: dict[int, Path] = {
    1: DIAGRAMAS / "casos_de_uso.png",
    2: DIAGRAMAS / "clases.png",
    3: DIAGRAMAS / "paquetes.png",
    4: DIAGRAMAS / "secuencia_01_reporte_online.png",
    5: DIAGRAMAS / "secuencia_02_offline_sync.png",
    6: DIAGRAMAS / "secuencia_03_confirmacion_arbitro.png",
    7: DIAGRAMAS / "secuencia_04_wordpress_ranking.png",
    8: DIAGRAMAS / "despliegue.png",
    9: DIAGRAMAS / "edt.png",
    10: MOCKUPS / "fig10-inicio-sesion.png",
    11: MOCKUPS / "fig11-registro.png",
    12: MOCKUPS / "fig12-inicio-usuario.png",
    13: MOCKUPS / "fig13-ranking-propio.png",
    14: MOCKUPS / "fig14-perfil-publico.png",
    15: MOCKUPS / "fig15-reporte-arbitro.png",
    16: MOCKUPS / "fig16-confirmacion.png",
    17: MOCKUPS / "fig17-reporte-jugador.png",
    18: MOCKUPS / "fig18-login-admin.png",
}

MARCA = "ESPACIO RESERVADO PARA FIGURA"


def _eliminar_parrafo(parrafo) -> None:
    """Quita un párrafo del árbol XML."""
    parrafo._element.getparent().remove(parrafo._element)


def _limpiar_texto(parrafo) -> None:
    """Elimina los runs (contenido) de un párrafo conservando su estilo/alineación."""
    for run in list(parrafo.runs):
        run._element.getparent().remove(run._element)


def _dimensiones(png: Path) -> tuple[int, int]:
    """Lee ancho/alto en píxeles de la cabecera IHDR del PNG (sin dependencias)."""
    import struct

    with png.open("rb") as fh:
        fh.read(16)  # firma (8) + longitud (4) + tipo 'IHDR' (4)
        ancho, alto = struct.unpack(">II", fh.read(8))
    return ancho, alto


def _ancho_ajustado(png: Path):
    """Calcula el ancho (EMU) para que la imagen quepa en ancho y alto máximos."""
    ancho_px, alto_px = _dimensiones(png)
    ancho = ANCHO_MAX
    alto = ancho * alto_px / ancho_px
    if alto > ALTO_MAX:
        alto = ALTO_MAX
        ancho = alto * ancho_px / alto_px
    return ancho


def _celdas_marcador(documento):
    """Devuelve {numero_figura: celda} para los 18 espacios reservados."""
    celdas: dict[int, object] = {}
    for tabla in documento.tables:
        for fila in tabla.rows:
            for celda in fila.cells:
                for parrafo in celda.paragraphs:
                    if MARCA in parrafo.text:
                        numero = int(parrafo.text.split(MARCA)[1].strip(" ]"))
                        celdas[numero] = celda
    return celdas


def insertar(docx_path: Path) -> int:
    """Inserta las 18 figuras y guarda el documento. Devuelve cuántas insertó."""
    documento = docx.Document(str(docx_path))
    celdas = _celdas_marcador(documento)

    faltantes = [n for n in FIGURAS if n not in celdas]
    if faltantes:
        raise SystemExit(
            f"No se encontraron los marcadores de las figuras: {faltantes}"
        )

    insertadas = 0
    for numero, png in FIGURAS.items():
        if not png.exists():
            raise SystemExit(f"Falta la imagen de la figura {numero}: {png}")
        celda = celdas[numero]

        # Primer párrafo = marcador; el segundo (si existe) = nota de ayuda.
        parrafos = celda.paragraphs
        principal = parrafos[0]
        for extra in parrafos[1:]:
            _eliminar_parrafo(extra)

        _limpiar_texto(principal)
        principal.alignment = WD_ALIGN_PARAGRAPH.CENTER
        principal.add_run().add_picture(str(png), width=_ancho_ajustado(png))
        insertadas += 1
        print(f"[OK] figura {numero}: {png.relative_to(RAIZ)}")

    documento.save(str(docx_path))
    return insertadas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", type=Path, default=DOCX_POR_DEFECTO)
    args = parser.parse_args()

    insertadas = insertar(args.docx)
    try:
        destino = args.docx.relative_to(RAIZ)
    except ValueError:
        destino = args.docx
    print(f"\n{insertadas} figuras insertadas en {destino}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
