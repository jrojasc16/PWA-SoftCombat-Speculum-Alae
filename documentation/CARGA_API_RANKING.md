# Informe de carga — GET /api/ranking (RNF002)

- **Fecha:** 2026-11-11
- **Requisito:** RNF002 — `GET /api/ranking` público, **p95 < 500 ms con 100 usuarios**, cacheable (RNF004).
- **Semilla:** `scripts/semillar_datos.py --reset` → 100 usuarios, 200 combates `CONFIRMADO`, 100 índices en el ranking.
- **Herramienta:** `scripts/cargar_api_ranking.py` (stdlib: `ThreadPoolExecutor` + `urllib`; servidor Werkzeug threaded en puerto efímero). Sin locust/ab (no instalados en el entorno).

## Resultado principal (caché activa, TTL = 300 s — configuración de despliegue)

5 ráfagas × 100 peticiones concurrentes = **500 peticiones**, todas `{200}`:

| métrica | valor |
|---|---|
| media | 108.6 ms |
| p50 | 119.0 ms |
| **p95** | **156.8 ms** |
| p99 | 180.9 ms |
| peor | 196.7 ms |

**RNF002: ✅ CUMPLE** (156.8 ms < 500 ms).

## Escenario estampida (peor caso real: invalidación + 100 en frío)

Cada recálculo Elo (confirmación de combate, edición admin, recálculo manual)
invalida la caché; el modo `--estampida` repite eso antes de cada ráfaga:

| métrica | valor |
|---|---|
| media | 204.0 ms |
| p50 | 216.8 ms |
| **p95** | **246.6 ms** |
| p99 | 251.4 ms |
| peor | 264.5 ms |

**RNF002: ✅ CUMPLE** (246.6 ms < 500 ms).

> **Corrección aplicada en esta tarea:** sin ella este escenario marcaba
> p95 ≈ 7 946 ms (100 peticiones en frío disparaban 100 queries a la vez).
> `public_api/services.py::ranking_publico` ahora ejecuta la consulta **bajo
> el lock** (*single-flight*): la primera petición consulta y guarda, el resto
> espera y sirve desde la caché. Verificado con 403 tests en verde.

## Diagnóstico: sin caché (TTL = 0, solo configuración de pruebas unitarias)

| métrica | valor |
|---|---|
| media | 4 697.8 ms |
| p50 | 4 855.9 ms |
| **p95** | **8 000.1 ms** |
| p99 | 8 153.7 ms |
| peor | 8 180.7 ms |

**RNF002: ❌ NO CUMPLE** — pero `RANKING_CACHE_TTL=0` **no es una
configuración de despliegue**: solo la usan las pruebas unitarias para mirar
a través de la caché. El requisito RNF002 exige el endpoint *cacheable*
(RNF004), y tanto dev como prod usan TTL = 300 s. Con 100 queries simultáneas
al ORM sobre SQLite el cuello de botella es el GIL de Python + la
materialización ORM (una consulta tuple pura ronda p95 ≈ 2.3 s en las mismas
condiciones); la caché es, por diseño, la que cumple el requisito.

## Cómo reproducirlo

```bash
# 1. Semilla (100 usuarios + 200 combates confirmados)
venv/bin/python scripts/semillar_datos.py --reset

# 2. Escenario principal (caché activa) — escribe el informe
venv/bin/python scripts/cargar_api_ranking.py \
    --usuarios 100 --rafagas 5 --informe documentation/CARGA_API_RANKING.md

# 3. Estampida (invalida la caché antes de cada ráfaga)
venv/bin/python scripts/cargar_api_ranking.py --usuarios 100 --rafagas 5 --estampida

# 4. Diagnóstico sin caché (TTL=0, no cumple; no es config. de despliegue)
venv/bin/python scripts/cargar_api_ranking.py --usuarios 100 --rafagas 5 --sin-ttl
```

## Contexto

- Datos: `scripts/semillar_datos.py` → 100 usuarios, 200 combates
  `CONFIRMADO`, 100 índices en el ranking (la hoja de cálculo del
  reglamento no aplica: los ratings rondan 1500 porque cada jugador tiene
  pocos duelos).
- Servidor: Werkzeug threaded (el mismo del desarrollo) escuchando en un
  puerto efímero de `127.0.0.1`.
- La p95 se calcula por interpolación lineal sobre las 500 latencias
  agregadas de las 5 ráfagas.
