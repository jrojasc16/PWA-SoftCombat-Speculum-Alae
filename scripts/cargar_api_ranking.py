#!/usr/bin/env python3
"""Prueba de carga de GET /api/ranking (Sprint 12.5, RNF002) con servidor propio.

Levanta la app Flask en un hilo (puerto efímero), calienta la caché y mide
p50/p95/p99 con ráfagas concurrentes. Objetivo del reglamento:
**p95 < 500 ms con 100 usuarios**.

Solo stdlib (urllib, ThreadPoolExecutor, threading): no requiere locust ni ab.

Uso (con la semilla ya cargada en instance/app.db):

    venv/bin/python scripts/cargar_api_ranking.py
    venv/bin/python scripts/cargar_api_ranking.py --usuarios 100 --rafagas 5 --informe documentation/CARGA_API_RANKING.md
"""

from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "prototype"))


def _percentil(valores: list[float], p: float) -> float:
    """Percentil por interpolación lineal sobre la lista ordenada."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    k = (len(ordenados) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordenados) - 1)
    return ordenados[f] + (ordenados[c] - ordenados[f]) * (k - f)


def _arrancar_servidor() -> tuple[object, str]:
    """Arranca la app en un hilo WSGI propio y devuelve (server, url base)."""
    import socket
    from werkzeug.serving import make_server

    from app import create_app

    app = create_app("development")
    # Puerto libre efímero.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]

    servidor = make_server("127.0.0.1", puerto, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return servidor, f"http://127.0.0.1:{puerto}"


def _una_peticion(url: str, timeout: float) -> tuple[float, int]:
    """Envía un GET y devuelve (latencia_ms, status_code)."""
    inicio = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            codigo = resp.status
    except urllib.error.HTTPError as exc:
        codigo = exc.code
    except Exception:
        codigo = 0
    return (time.perf_counter() - inicio) * 1000.0, codigo


def _rafaga(url: str, n: int, timeout: float) -> list[tuple[float, int]]:
    """Ejecuta ``n`` peticiones concurrentes (una «ráfaga»)."""
    resultados: list[tuple[float, int]] = []
    with ThreadPoolExecutor(max_workers=max(n, 1)) as pool:
        futuros = [pool.submit(_una_peticion, url, timeout) for _ in range(n)]
        for fut in as_completed(futuros):
            resultados.append(fut.result())
    return resultados


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga de GET /api/ranking (RNF002).")
    parser.add_argument("--usuarios", type=int, default=100, help="Concurrencia por ráfaga.")
    parser.add_argument("--rafagas", type=int, default=5, help="Número de ráfagas.")
    parser.add_argument(
        "--por-rafaga",
        type=int,
        default=None,
        help="Peticiones por ráfaga (por defecto = --usuarios).",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--calentamiento", type=int, default=20, help="PETs previas.")
    parser.add_argument("--sin-ttl", action="store_true", help="Fuerza RANKING_CACHE_TTL=0 (peor caso: BD).")
    parser.add_argument(
        "--estampida",
        action="store_true",
        help="Vacia la caché antes de cada ráfaga (peor caso real: recálculo Elo + 100 en frío).",
    )
    parser.add_argument("--informe", default=None, help="Ruta Markdown del informe.")
    args = parser.parse_args()

    por_rafaga = args.por_rafaga or args.usuarios

    servidor, base = _arrancar_servidor()
    url = f"{base}/api/ranking"
    if args.sin_ttl:
        servidor.app.config["RANKING_CACHE_TTL"] = 0
    ttl = servidor.app.config.get("RANKING_CACHE_TTL", 300)
    print(f"Servidor en {url} (RANKING_CACHE_TTL={ttl})")

    try:
        # Comprobación previa: debe responder 200 con items.
        _, codigo0 = _una_peticion(url, args.timeout)
        if codigo0 != 200:
            print(f"GET /api/ranking respondió {codigo0}: ¿semilla cargada?", file=sys.stderr)
            return 2

        print(f"Calentamiento: {args.calentamiento} peticiones…")
        for _ in range(args.calentamiento):
            _una_peticion(url, args.timeout)

        latencias: list[float] = []
        codigos: dict[int, int] = {}

        for i in range(args.rafagas):
            if args.estampida:
                # Invalida la caché como haría un recálculo Elo on-write.
                from app.modules.public_api import services as servicios_publicos

                servicios_publicos.invalidar_cache()
            t0 = time.perf_counter()
            lote = _rafaga(url, por_rafaga, args.timeout)
            wall = (time.perf_counter() - t0) * 1000.0
            for ms, codigo in lote:
                latencias.append(ms)
                codigos[codigo] = codigos.get(codigo, 0) + 1
            print(
                f"  Ráfaga {i + 1}/{args.rafagas}: {por_rafaga} PETs, "
                f"wall={wall:.0f} ms, p95_ráfaga={_percentil([m for m, _ in lote], 95):.1f} ms"
            )
    finally:
        servidor.shutdown()

    if not latencias:
        print("Sin resultados.", file=sys.stderr)
        return 1

    p50 = _percentil(latencias, 50)
    p95 = _percentil(latencias, 95)
    p99 = _percentil(latencias, 99)
    media = statistics.fmean(latencias)
    peor = max(latencias)
    ok = all(c == 200 for c in codigos)
    cumple = p95 < 500.0

    print()
    print("=== Resultado GET /api/ranking ===")
    print(f"  Ráfagas:          {args.rafagas} × {por_rafaga} PETs concurrentes")
    print(f"  Peticiones tot.:  {len(latencias)}")
    print(f"  Códigos HTTP:     {dict(sorted(codigos.items()))}")
    print(f"  TTL caché:        {ttl}")
    print(f"  media:            {media:.1f} ms")
    print(f"  p50:              {p50:.1f} ms")
    print(f"  p95:              {p95:.1f} ms  (objetivo < 500 ms)")
    print(f"  p99:              {p99:.1f} ms")
    print(f"  peor:             {peor:.1f} ms")
    print(f"  RNF002:           {'CUMPLE' if cumple else 'NO CUMPLE'}")

    if args.informe:
        lineas = [
            "# Informe de carga — GET /api/ranking (RNF002)",
            "",
            f"- **Fecha:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Semilla:** {args.usuarios} usuarios concurrentes × {args.rafagas} ráfagas "
            f"({por_rafaga} PETs c/u) = **{len(latencias)} peticiones**, todas respondidas con "
            f"`{dict(sorted(codigos.items()))}`.",
            f"- **Caché en memoria del endpoint:** TTL = {ttl} s "
            f"({'peor caso sin caché (directo a BD)' if ttl <= 0 else 'activa tras calentamiento'}).",
            "",
            "| métrica | valor |",
            "|---|---|",
            f"| media | {media:.1f} ms |",
            f"| p50 | {p50:.1f} ms |",
            f"| **p95** | **{p95:.1f} ms** |",
            f"| p99 | {p99:.1f} ms |",
            f"| peor | {peor:.1f} ms |",
            "",
            f"**RNF002 (p95 < 500 ms con 100 usuarios): "
            f"{'✅ CUMPLE' if cumple else '❌ NO CUMPLE'}**",
            "",
            "## Cómo reproducirlo",
            "",
            "```bash",
            "# 1. Semilla (100 usuarios + 200 combates confirmados)",
            "venv/bin/python scripts/semillar_datos.py --reset",
            "",
            "# 2. Carga (levantado servidor incluido en el script)",
            "venv/bin/python scripts/cargar_api_ranking.py \\",
            "    --usuarios 100 --rafagas 5 --informe documentation/CARGA_API_RANKING.md",
            "",
            "# Variante peor caso (sin caché, consulta directa a SQLite):",
            "venv/bin/python scripts/cargar_api_ranking.py --sin-ttl --rafagas 5",
            "```",
            "",
            "## Contexto",
            "",
            "- Datos: `scripts/semillar_datos.py` → 100 usuarios, 200 combates "
            "`CONFIRMADO`, 100 índices en el ranking (la hoja de cálculo del "
            "reglamento no aplica: los ratings rondan 1500 porque cada jugador "
            "pocos duelos).",
            "- Servidor: Werkzeug threaded (el mismo del desarrollo) escuchando en "
            "un puerto efímero de `127.0.0.1`.",
            "- Herramienta: `scripts/cargar_api_ranking.py` (Python stdlib: "
            "`ThreadPoolExecutor` + `urllib`). Sin dependencias externas.",
            "",
        ]
        Path(args.informe).write_text("\n".join(lineas), encoding="utf-8")
        print(f"  Informe escrito en {args.informe}")

    return 0 if (ok and cumple) else 1


if __name__ == "__main__":
    raise SystemExit(main())
