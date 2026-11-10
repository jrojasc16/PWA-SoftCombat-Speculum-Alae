"""Verificación automática de los criterios de instalabilidad de la PWA (Sprint 8.4).

Comprueba, contra una instancia en marcha, todo lo que exigen Chrome, Edge,
Firefox y Safari para considerar instalable la aplicación:

1. ``manifest.json`` válido y completo (nombre, ``start_url``, ``scope``,
   ``display: standalone``, colores e iconos de 192 y 512 px).
2. Iconos PNG descargables y con las dimensiones declaradas.
3. Layout enlazado al manifest, con ``theme-color`` e iconos.
4. ``start_url`` y la página de respaldo ``/offline`` respondiendo 200.
5. Service worker descargable, con manejador ``fetch`` y con
   ``Service-Worker-Allowed: /`` (si no, su alcance quedaría en ``/static/``).
6. Origen seguro: la instalación real exige HTTPS (o ``localhost``).

Uso:

    venv/bin/python prototype/run.py            # en otra terminal
    venv/bin/python scripts/verificar_pwa.py --url http://127.0.0.1:5000

Devuelve 0 si todos los criterios pasan y 1 si hay alguno fallido.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

USER_AGENT = "verificador-pwa-speculum-alae/1.0"


@dataclass
class Resultado:
    """Resultado de un criterio de verificación."""

    nombre: str
    ok: bool
    detalle: str = ""
    informativo: bool = False


@dataclass
class Informe:
    """Conjunto de resultados de la verificación."""

    resultados: list[Resultado] = field(default_factory=list)

    def agregar(self, nombre, ok, detalle="", informativo=False):
        self.resultados.append(Resultado(nombre, ok, detalle, informativo))
        return ok

    @property
    def fallos(self) -> list[Resultado]:
        return [r for r in self.resultados if not r.ok and not r.informativo]

    def imprimir(self) -> None:
        for resultado in self.resultados:
            if resultado.informativo:
                marca = "INFO"
            elif resultado.ok:
                marca = " OK "
            else:
                marca = "FALLA"
            print(f"[{marca}] {resultado.nombre}: {resultado.detalle}")


def _contexto(url: str):
    if url.startswith("https://"):
        return ssl.create_default_context()
    return None


def _descargar(url: str) -> tuple[int, bytes, dict]:
    """Descarga una URL devolviendo (código, cuerpo, cabeceras)."""
    peticion = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    contexto = _contexto(url)
    try:
        with urllib.request.urlopen(peticion, timeout=15, context=contexto) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def _dimensiones_png(datos: bytes) -> tuple[int, int] | None:
    """Dimensiones de un PNG (IHDR) o ``None`` si el archivo no es PNG."""
    if datos[:8] != b"\x89PNG\r\n\x1a\n" or len(datos) < 24:
        return None
    return (
        int.from_bytes(datos[16:20], "big"),
        int.from_bytes(datos[20:24], "big"),
    )


def verificar(url_base: str) -> Informe:
    """Ejecuta todos los criterios de instalabilidad sobre ``url_base``."""
    informe = Informe()
    base = url_base.rstrip("/")

    # --- 1. Manifest ------------------------------------------------------
    try:
        estado, cuerpo, _ = _descargar(f"{base}/static/manifest.json")
    except OSError as exc:
        informe.agregar("Manifest descargable", False, f"no se pudo descargar: {exc}")
        return informe

    if estado != 200:
        informe.agregar("Manifest descargable", False, f"HTTP {estado}")
        return informe
    informe.agregar("Manifest descargable", True, "HTTP 200 en /static/manifest.json")

    try:
        manifest = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        informe.agregar("Manifest con JSON válido", False, str(exc))
        return informe
    informe.agregar("Manifest con JSON válido", True, "JSON correcto")

    for campo in ("name", "short_name", "start_url", "scope"):
        valor = manifest.get(campo)
        informe.agregar(
            f"Manifest con «{campo}»",
            bool(valor),
            str(valor) if valor else "falta en el manifest",
        )

    informe.agregar(
        "Manifest con display standalone",
        manifest.get("display") == "standalone",
        f"display={manifest.get('display')!r}",
    )

    for campo in ("theme_color", "background_color"):
        valor = manifest.get(campo)
        informe.agregar(
            f"Manifest con «{campo}»",
            isinstance(valor, str) and valor.startswith("#"),
            str(valor) if valor else "falta en el manifest",
        )

    # --- 2. Iconos --------------------------------------------------------
    iconos = manifest.get("icons", [])
    tamanos = {str(icono.get("sizes")) for icono in iconos}
    informe.agregar(
        "Manifest con iconos de 192 y 512 px",
        {"192x192", "512x512"} <= tamanos,
        f"sizes={sorted(tamanos)}",
    )

    for icono in iconos:
        src = icono.get("src", "")
        lado = int(str(icono.get("sizes", "0x0")).split("x")[0] or 0)
        try:
            estado, cuerpo_icono, cabeceras = _descargar(base + src)
        except OSError as exc:
            informe.agregar(f"Icono {src}", False, f"no se pudo descargar: {exc}")
            continue
        tipo = cabeceras.get("Content-Type", "")
        dimensiones = _dimensiones_png(cuerpo_icono) if estado == 200 else None
        ok = (
            estado == 200
            and tipo.startswith("image/png")
            and dimensiones == (lado, lado)
        )
        informe.agregar(
            f"Icono {src}",
            ok,
            f"HTTP {estado}, tipo {tipo}, dimensiones {dimensiones}",
        )

    # --- 3. Layout enlazado ----------------------------------------------
    try:
        estado, cuerpo_html, _ = _descargar(f"{base}/")
        html = cuerpo_html.decode("utf-8", "replace")
    except OSError as exc:
        estado, html = 0, ""
        informe.agregar("Layout enlazado al manifest", False, str(exc))
    else:
        tiene_manifest = 'rel="manifest"' in html
        tiene_theme = 'name="theme-color"' in html
        informe.agregar(
            "Layout enlazado al manifest",
            estado == 200 and tiene_manifest,
            f"HTTP {estado}, rel=manifest: {tiene_manifest}",
        )
        informe.agregar(
            "Layout con theme-color",
            tiene_theme,
            "meta theme-color presente" if tiene_theme else "falta meta theme-color",
        )

    # --- 4. Páginas clave -------------------------------------------------
    for ruta, etiqueta in (("/ranking", "start_url"), ("/offline", "respaldo sin conexión")):
        try:
            estado, _, _ = _descargar(base + ruta)
        except OSError as exc:
            informe.agregar(f"Página {etiqueta}", False, str(exc))
            continue
        informe.agregar(f"Página {etiqueta}", estado == 200, f"{ruta} → HTTP {estado}")

    # --- 5. Service worker ------------------------------------------------
    try:
        estado, cuerpo_sw, cabeceras = _descargar(f"{base}/static/sw.js")
    except OSError as exc:
        informe.agregar("Service worker descargable", False, str(exc))
    else:
        sw = cuerpo_sw.decode("utf-8", "replace")
        informe.agregar(
            "Service worker descargable",
            estado == 200,
            f"HTTP {estado}",
        )
        informe.agregar(
            "Service worker con manejador fetch",
            'addEventListener("fetch"' in sw,
            "registra el evento fetch" if 'addEventListener("fetch"' in sw else "sin fetch",
        )
        permitido = cabeceras.get("Service-Worker-Allowed")
        informe.agregar(
            "Service worker con alcance en la raíz",
            permitido == "/",
            f"Service-Worker-Allowed={permitido!r}",
        )

    # --- 6. Origen seguro -------------------------------------------------
    es_local = url_base.startswith("http://127.0.0.1") or url_base.startswith(
        "http://localhost"
    )
    informe.agregar(
        "Origen seguro para instalar",
        url_base.startswith("https://") or es_local,
        "HTTPS" if url_base.startswith("https://") else ("localhost" if es_local else "HTTP: la instalación exige HTTPS en producción"),
        informativo=es_local,
    )

    return informe


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument(
        "--url", default="http://127.0.0.1:5000", help="Base URL de la app en marcha"
    )
    argumentos = analizador.parse_args()

    informe = verificar(argumentos.url)
    informe.imprimir()

    if informe.fallos:
        print(f"\nCriterios fallidos: {len(informe.fallos)}")
        return 1
    print("\nTodos los criterios de instalabilidad se cumplen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
