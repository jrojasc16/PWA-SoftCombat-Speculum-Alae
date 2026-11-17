# Estado del despliegue en producción — Speculum-Alae (Sprint 14, tareas 14.1–14.3)

- **Fecha:** 2026-11-12 · **Rama:** `desarrollo-sprint-7`
- **Objetivo:** publicar el prototipo en PythonAnywhere (plan gratuito) con HTTPS
  (RNF001) y validarlo de extremo a extremo.

## Resumen

| tarea | estado | nota |
|---|---|---|
| **14.1** Cuenta/app + `ProductionConfig` + HTTPS + `SECRET_KEY` | **Verificado en local; pendiente la cuenta real** | `ProductionConfig` y `wsgi.py` funcionan; falta crear la cuenta/app y generar la `SECRET_KEY` en PA |
| **14.2** Despliegue (código → requirements → migraciones → reload) | **Procedimiento listo; pendiente ejecutarlo en PA** | comandos exactos en `DEPLOY_PYTHONANYWHERE.md`; migraciones probadas con el entrypoint real |
| **14.3** Smoke test en producción | **Equivalente local PASS (12/12); pendiente contra la URL pública** | `scripts/verificar_produccion_local.py`; el test contra PA requiere la URL real |

> **Bloqueo externo:** las tareas 14.1–14.3 necesitan una **cuenta de
> PythonAnywhere** (credenciales del equipo) y el **push** de la rama al remoto.
> Sin ellos no es posible crear la app ni alcanzar la URL pública desde este
> entorno. Los pasos manuales quedan abajo; el resto ya está validado.

## Evidencia del pre-flight local (14.1–14.3)

`venv/bin/python scripts/verificar_produccion_local.py` → **12/12 comprobaciones OK**:

- `wsgi.py` (el **mismo** entrypoint de producción) arranca en `ProductionConfig`
  con `SECRET_KEY` por entorno y `SESSION_COOKIE_SECURE=True`.
- Esquema creado con el **comando real del despliegue**
  (`flask --app wsgi.py db upgrade`, que además siembra los 4 roles).
- `GET /health` → 200 `{"env":"production","status":"ok"}`.
- `GET /api/ranking` → 200 JSON con `Cache-Control: public…`.
- `GET /login` y `GET /ranking` → 200.
- `GET /me` sin sesión → **401 JSON** (nunca redirección).
- HTTPS forzado tras proxy: `X-Forwarded-Proto: http` → **308** a `https://`.
- Ciclo completo bajo `ProductionConfig`: registro → reporte → confirmación dual
  → **CONFIRMADO + Elo on-write** → ranking público sin correos.

## Checklist para ejecutar el despliegue real (usuario)

1. **Push del código** (requisito de `git clone` en PA):
   `git push -u origin desarrollo-sprint-7`.
2. **Cuenta e imagen** — cuenta gratuita universitaria del equipo; Python 3.12
   (`DEPLOY_PYTHONANYWHERE.md` §1).
3. **Código, venv e instalación** (§2–§3): `git clone` + `pip install -r
   prototype/requirements.txt`.
4. **`SECRET_KEY` y `.env`** (§4): `python -c "import secrets;
   print(secrets.token_hex(32))"` → `prototype/.env` (`chmod 600`). *La app no
   arranca en producción sin ella (`RuntimeError` intencionado).*
5. **Migraciones** (§5): `flask --app wsgi.py db upgrade`.
6. **Pestaña Web** (§6): manual configuration con Python 3.12, *source* =
   `…/prototype`, venv `sa-venv`, **sin mapear estáticos** (por
   `Service-Worker-Allowed: /`), WSGI apuntando a `prototype/wsgi.py`, **Force
   HTTPS** activado, *Reload*.
7. **Smoke en producción** (§7): `https://<usuario>.pythonanywhere.com/health`
   → `{"env":"production","status":"ok"}`; luego registro → combate con dos
   confirmaciones → ranking actualizado.
8. **Registrar la URL y la fecha de vencimiento** en la bitácora de
   `MANUAL_OPERACION.md` §9.

## Comando de re-verificación (cada cambio de despliegue)

```bash
venv/bin/python scripts/verificar_produccion_local.py   # 12/12 OK en local
# y, contra la URL pública, el checklist §7 de DEPLOY_PYTHONANYWHERE.md
```
