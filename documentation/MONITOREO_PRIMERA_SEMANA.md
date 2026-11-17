# Monitoreo de la primera semana en producción (Sprint 14, tarea 14.4)

Guía breve para vigilar el prototipo durante los primeros días tras el
despliegue. Detalle ampliado en `documentation/MANUAL_OPERACION.md`.

> **Nota sobre caducidad:** el plan gratuito de PythonAnywhere **expira la web
> app al mes** (hay que renovarla con el botón «run until» de la pestaña Web).
> El PLAN de desarrollo menciona «cada 3 meses»; el dato correcto y vigente es
> **mensual** (`DEPLOY_PYTHONANYWHERE.md` §0/§9). Anotar la renovación el mismo
> día del despliegue de cada mes.

## Qué revisar (y cada cuánto)

| cuándo | chequeo | señal de alarma |
|---|---|---|
| Tras el despliegue | `/health` → `{"env":"production","status":"ok"}` | 404 (app caducada/sin recargar), 502/500 |
| Cada mañana (semana 1) | *Web → Error log* y *Server log* | trazas repetidas, `sqlite3.OperationalError` |
| Cada mañana | `GET /api/ranking` responde < 500 ms | lentitud (¿caché invalidada a menudo?) |
| Diario | Consumo de CPU (pestaña *Consoles*) | picos de 100 s/día por scripts en consola |
| Una vez | Probar la PWA offline (instalar + modo avión) | ranking sin copia cacheada |
| Al cerrar la semana | Revisar roles/usuarios en `/admin`; conflictos pendientes | conflictos acumulados sin resolver |

## Acciones rápidas ante incidentes

| síntoma | acción | sección |
|---|---|---|
| 404 de PA | renovar la web app | `MANUAL_OPERACION.md` §4.1 |
| `RuntimeError: SECRET_KEY no definida` | revisar `prototype/.env` y el WSGI; *Reload* | §4.4 / §7 |
| 500 en una vista | *Error log* → corregir → `git pull`/editar → *Reload* | §4.4 |
| Ranking descuadrado | «Recalcular ranking» en `/admin` | §4.6 |
| PWA sin caché | quitar *static files* mapeados en PA | §7 |
| `database is locked` | dejar de escribir desde consolas; usar solo la web app | §7 |

## Registro de la primera semana (rellenar)

| día | `/health` | errores en log | CPU s/día | incidencias | responsable |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |
| 7 | | | | | |

## Renovación y límites (resumen)

- **Renovación: mensual** (botón «run until»); aviso por correo de PA.
- **Plan gratuito:** 1 web app (1 worker), 100 CPU-s/día de consola, 512 MiB,
  sin MySQL/cron/dominio propio (detalle en `MANUAL_OPERACION.md` §6).
- **Escalar a pago** si se necesita dominio propio, más workers o backups
  automáticos.
