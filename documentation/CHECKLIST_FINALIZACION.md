# Checklist de finalización del proyecto — Speculum-Alae Ranking App

**Fecha de corte:** 2026-11-09 · **Rama de trabajo:** `desarrollo-sprint-7` · **Plan maestro:** `documentation/PLAN_DESARROLLO_PROTOTIPO.md`

---

## 0. Estado actual (verificado)

| Ítem | Estado |
|---|---|
| Sprints 1–8 | Completados y marcados en el plan |
| Sprint 8 | **Completado** (commits `6a1c2ad`, `92b371e`, `48fcd60`, `580b7ff`, `2d10c3a`): manifest + iconos, SW stale-while-revalidate con marca de tiempo, indicador offline, verificador de instalabilidad, pruebas manuales documentadas. La ejecución con navegador real (instalación y modo avión) queda pendiente para el equipo |
| Sprint 9 | **Completado** (commits `8d4d758`, `e71ea3e`, `0d5240f`, `fe71eed`, `86feffe` + `a850eb7`): cola `outbox` en IndexedDB, drenaje FIFO con backoff, idempotencia `client_request_id`, lista de pendientes en `/reportar`, diagramas actualizados. Verificado en Microsoft Edge headless (9 pasos OK) |
| Working tree | Limpio salvo este documento de trabajo (`documentation/CHECKLIST_FINALIZACION.md`) |
| Push al remoto | **Pendiente** — la rama `desarrollo-sprint-7` no existe en `origin` (42 commits locales) |
| Entregables "stub" | `prototype/docs/openapi.yaml` (1 línea), `prototype/wordpress-plugin/ranking-table.php` (5 líneas), `prototype/app/static/db.js` (6 líneas) |
| Diagramas | Fuentes `.puml`/`.mmd` existentes, **sin PNG exportados** (requerido por 18 espacios reservados del `.docx` v2) |
| Documentación | `.docx` v2 redactado; faltan las figuras PNG |
| Código | Todo vive en `prototype/`; `code/` sigue reservado (vacío) |

Comando de verificación local: `cd prototype && ../venv/bin/python -m pytest -q` (o `scripts/check.sh`).

---

## Bloque 0 — Cierres administrativos inmediatos (antes de seguir)

- [ ] **0.1** ~~Commitear el trabajo parcial del Sprint 8~~ — **hecho** (commits `6a1c2ad` … `2d10c3a`).
- [ ] **0.2** Ejecutar `git push -u origin desarrollo-sprint-7` (lo ejecuta el usuario con sus credenciales; este entorno no tiene acceso a GitHub).
- [ ] **0.3** Verificar con `git status -sb` que la rama queda siguiendo el remoto y sin cambios pendientes.
- [ ] **0.4** Decidir el destino de `code/` (vacío): eliminarlo o dejar constancia en el README de que el código vive en `prototype/`.
- [ ] **0.5** Confirmar con el supervisor la transición de stack aprobada (Flask + SQLite + PWA) antes del cierre del Sprint 14, ya que el `.docx` v1.0 sigue siendo la referencia histórica.

---

## Sprint 8 — PWA: manifest, service worker y lectura offline — **COMPLETADO**

- [x] **8.1** `manifest.json` con nombre, iconos 192/512, `start_url`, `display: standalone`, colores → commit `6a1c2ad` (iconos generados con `scripts/generar_iconos_pwa.py`, favicon/apple-touch-icon, `theme-color`, paleta CSS, tests del manifest y de los PNG).
- [x] **8.2** `static/sw.js`: app-shell (precache de layout/CSS/JS) + runtime cache del ranking e historial propio con marca de tiempo y estrategia *stale-while-revalidate* → commit `92b371e` (SWR de `/api/ranking` y `/me/history`, cabecera `X-SW-Cache-Time`, mensajes `sa-cache-actualizada`, `sa-estado-cache`, `sa-limpiar-cache`, `sa-datos-cache`).
- [x] **8.3** Registro del SW desde el layout; indicador visual de “modo offline / datos de las HH:MM” → commit `48fcd60` (banner `#aviso-offline`, marca `#marca-datos`, listeners `online`/`offline`, purga al cerrar sesión, página pública `/offline`).
- [x] **8.4** Verificar instalabilidad (Lighthouse: installable en Android y escritorio; RNF005: Chrome/Firefox/Edge/Safari, 2 últimas versiones) → commit `580b7ff` (`scripts/verificar_pwa.py`, test en CI con servidor efímero, informe `documentation/PWA_VERIFICACION_INSTALABILIDAD.md`; la medición con Lighthouse queda como paso manual documentado).
- [x] **8.5** Pruebas manuales documentadas: cargar ranking online → bajar a modo avión → recargar → se muestra la copia cacheada → commit `2d10c3a` (`documentation/PRUEBAS_MANUALES_PWA.md`, 8 casos + registro de ejecución).
- [ ] **Pendiente del equipo (no automatizable aquí):** ejecutar los 8 casos manuales con navegador y llenar la tabla de registro de `documentation/PRUEBAS_MANUALES_PWA.md`.

---

## Sprint 9 — Outbox offline (IndexedDB) y sincronización — **COMPLETADO**

- [x] **9.1** `static/db.js`: wrapper de IndexedDB con store `outbox` (payload + `client_request_id` + timestamp) y store `directorio` → commit `8d4d758`.
- [x] **9.2** Al reportar sin conexión → encolar; al recuperar red (`online` + al abrir) → drenar la cola **en orden**, con reintento y backoff exponencial → commit `e71ea3e` (`static/js/sync.js`).
- [x] **9.3** Reutilizar `client_request_id` (Sprint 4.5) para que el servidor descarte duplicados sin error visible → commit `0d5240f` (clave generada antes de enviar, reutilizada en el reintento; 200 = «ya estaba registrado»).
- [x] **9.4** UI: listado de «reportes pendientes de envío» con estado por ítem en `/reportar` → commit `fe71eed`.
- [x] **9.5** Diagramas `secuencia_02_offline_sync.{puml,mmd}` actualizados con el flujo real → commit `86feffe`.
- [x] **Verificación del sprint** en navegador real (Microsoft Edge headless): `scripts/verificar_offline_browser.py` + `scripts/harness_offline.html` + `scripts/cdp_esperar_resultado.mjs` → commit `a850eb7` (9 pasos OK).

---

## Sprint 10 — Panel de administración completo — **COMPLETADO**

- [x] **10.1** Vista `/admin` protegida por rol, con menú: usuarios, combates en conflicto, recálculo → commit `3437e32` (`role_required_html` en `app/shared/decorators.py`: 302 sin sesión, 403 con rol insuficiente; `admin/panel.html`; enlace «Admin» solo para `admin`/`super_admin`).
- [x] **10.2** Gestión de usuarios: listar, activar/desactivar, cambiar rol (`admin`/`super_admin` únicamente) → commit `a019e26` (API nueva `GET /admin/users` y `PATCH|POST /admin/users/<id>`; página `/admin/panel/usuarios`; aislamiento por comunidad RNF006; sin auto-desactivación ni auto-cambio de rol; solo `super_admin` concede `super_admin`).
- [x] **10.3** Lista de combates `CONFLICTO` con formulario de edición → `PATCH /admin/combats/<id>` y visualización del `AuditLog` por combate → commit `d7245fd` (página `/admin/panel/combates` con filtro por estado; endpoint nuevo `GET /admin/combats/<id>/audit`; la bitácora también aísla por comunidad).
- [x] **10.4** Botón “Recalcular ranking” → `POST /admin/ranking/recalculate` con confirmación previa y resultado (n.º de combates reprocesados) → commit `2472f48` (`window.confirm` + mensaje `#estado-recalculo`).
- [x] **10.5** Tests de permisos en todas las rutas nuevas (401/403 por rol y comunidad) → commit `07d9df5` (`prototype/tests/test_admin_panel.py`, 34 tests).
- [x] **10.6** Sprint marcado en el plan y commit por tarea → commit `Sprint 10, tarea 10.6` (este commit).
- [x] **Verificación del sprint** en navegador real (Microsoft Edge headless): `scripts/verificar_admin_browser.py` + `scripts/harness_admin.html` + CDP → 17 pasos OK (403 del jugador en la página y en la API, gestión de usuarios, auto-desactivación bloqueada, resolución de conflictos, bitácora con `winner_id` y `status`, recálculo del ranking). **357 tests en verde**, cobertura `app.modules.ranking` = 100 %.

---

## Sprint 11 — Plugin WordPress + shortcode `[ranking_table]`

> **Estado: 11.1–11.3 completados (3 de 5 tareas = la mitad del sprint).** 11.4 y 11.5 pendientes.

- [x] **11.1** `prototype/wordpress-plugin/ranking-table.php`: cabecera de plugin, registro del shortcode, consumo de `GET /api/ranking` con la HTTP API de WP → commit `0f6ac4b`. Shortcode `[ranking_table]` con atributos `community_id`/`per_page` (mismos límites que `shared/http.py`), tabla con las mismas columnas/orden/mensaje vacío que `templates/ranking.html`.
- [x] **11.2** Caché con **Transients** (TTL ≈ 5 min) y mensaje degradado si el backend no responde → commit `8a7dd6e`. Flujo: caché vivo → API → **respaldo sin caducidad** (última copia marcada como desactualizada) → mensaje degradado; `timeout` de 5 s en la petición.
- [x] **11.3** Página de ajustes: URL base de la API + TTL → commit `6290ccb` (`Ajustes → Ranking SA`, Settings API; URL solo http/https, TTL 0–86400 s con 0 = sin caché; al guardar se vacía el caché).
- [ ] **11.4** Escapado de toda salida (`esc_html`, `esc_attr`) y tabla HTML ordenada igual que la vista web. — *El código ya escapa toda la salida y replica columnas/orden/mensaje vacío; falta la revisión formal (incluye comprobar visualmente contra la vista `/ranking`).*
- [ ] **11.5** Prueba en un WordPress local/staging con datos reales del prototipo (y 11.6: apuntar el shortcode a producción en el Sprint 14). — *Requiere un WordPress del equipo; el entorno de desarrollo no tiene PHP.*
- **Verificación parcial:** 26 tests de contrato en `prototype/tests/test_plugin_wordpress.py` (cabecera WP, shortcode, contrato de query string vs. `public_api/routes.py`, límites de paginación vs. `shared/http.py`, columnas vs. `ranking.html`, flujo de caché, sanitizadores, guardia `manage_options`). **383 tests en verde**, cobertura `app.modules.ranking` = 100 %. Sin `php -l` disponible en el entorno.

---

## Sprint 12 — Pruebas integrales, carga y OpenAPI

- [ ] **12.1** Completar `prototype/docs/openapi.yaml` (hoy es una línea de docstring) con **todos** los endpoints: auth, combates, confirmaciones, ranking público, admin, historial; esquemas y códigos de error.
- [ ] **12.2** Validar el OpenAPI (linter/validador) y referenciarlo en el README.
- [ ] **12.3** Suite de integración end-to-end: registro → reporte → confirmación dual → ranking actualizado → historial → endpoint público.
- [ ] **12.4** Script de semilla de datos: 100 usuarios + N combates confirmados.
- [ ] **12.5** Prueba de carga sobre `GET /api/ranking` (`locust`/`ab`): **p95 < 500 ms con 100 usuarios** (RNF002) y documentar resultados.
- [ ] **12.6** Revisión de seguridad: bcrypt costo 12 efectivo, cookies `Secure`/`HttpOnly`, HTTPS forzado en producción, sin datos sensibles en respuestas públicas.
- [ ] **12.7** Confirmar cobertura Elo ≥ 70 % (hoy 100 %) con `scripts/check.sh` y artefactos de CI.

---

## Sprint 13 — Documentación técnica y de usuario

- [ ] **13.1** `prototype/README.md`: instalar, migrar (`flask db upgrade`), correr (`run.py`/`wsgi.py`), testear — en español.
- [ ] **13.2** Guía de despliegue en PythonAnywhere: variables de entorno, `SECRET_KEY`, `wsgi.py`, dominio y HTTPS.
- [ ] **13.3** Manual de usuario breve por rol (jugador, árbitro, admin) con capturas de pantalla.
- [ ] **13.4** **Exportar los PNG de `documentation/diagrams/`** (hoy no existe ninguno) e insertarlos en los **18 espacios reservados** del `.docx` v2 (`documentation/Metodologia_Proyecto_Ingenieria_Software_Speculum_Alae_v2_PWA.docx`), revisando coherencia figura ↔ texto.
- [ ] **13.5** Sincronizar `documentation/diagrams/clases.puml` **y** `.mmd` con la implementación real (`Confirmation.reported_result`, `AuditLog.campo/valor_anterior/valor_nuevo`) — pendiente declarado en `AGENTS.md`.
- [ ] **13.6** Actualizar `AGENTS.md` (estado de sprints, superficie HTTP, ramas, estado del push).
- [ ] **13.7** Manual de operación: renovación de cuenta, respaldos de SQLite, plan gratuito de PythonAnywhere.

---

## Sprint 14 — Despliegue en producción y buffer

- [ ] **14.1** Cuenta/app en PythonAnywhere con `ProductionConfig`, HTTPS del subdominio (RNF001) y `SECRET_KEY` fuerte por variable de entorno.
- [ ] **14.2** Despliegue: código → `pip install -r requirements.txt` → `flask db upgrade` → seed de roles → recarga web.
- [ ] **14.3** Smoke test en producción: registro, combate completo (2 confirmaciones), ranking público, shortcode de WordPress apuntando a producción.
- [ ] **14.4** Monitoreo de la primera semana (revisión de logs de error), documentar renovación manual (cada 3 meses) y limitaciones del plan gratuito.
- [ ] **14.5** Buffer de contingencia: atender pendientes/bugs de sprints anteriores.
- [ ] **14.6** Retrospectiva final y **acta de cierre** del proyecto.

---

## Cierre del proyecto — lista de entregables

- [ ] Código completo en `prototype/` en la rama `desarrollo-sprint-7`, **push al remoto hecho**.
- [ ] `prototype/docs/openapi.yaml` completo y validado.
- [ ] `prototype/wordpress-plugin/ranking-table.php` funcional.
- [ ] `prototype/README.md` + guía de despliegue + manual de usuario.
- [ ] `.docx` v2 con las 18 figuras insertadas (no modificar el v1.0).
- [ ] Diagramas `.puml`/`.mmd` sincronizados con la implementación + PNG exportados.
- [ ] Evidencia de pruebas: 272+ tests en verde, cobertura ranking ≥ 70 %, artefactos de CI.
- [ ] Evidencia de carga (p95 < 500 ms / 100 usuarios) documentada.
- [ ] Checklist de `documentation/PLAN_DESARROLLO_PROTOTIPO.md` con los 14 sprints marcados.
- [ ] `AGENTS.md` actualizado.
- [ ] Acta de cierre firmada/entregada al supervisor.

---

## Riesgos / puntos de atención

1. **Rama sin remoto**: hasta que se haga `git push -u origin desarrollo-sprint-7`, todo el trabajo (50+ commits) existe solo en local.
2. **PNG de diagramas inexistentes**: bloquea el 13.4; requiere PlantUML (Java) o Graphviz para exportar `.puml`.
3. ~~**Endpoints admin de usuarios inexistentes**~~ — **resuelto en el Sprint 10.2** (API nueva `GET /admin/users` y `PATCH|POST /admin/users/<id>`, commit `a019e26`).
4. **RNF003 / RNF005** están definidos en `PROPUESTA_NUEVO_STACK.md` §7 (no inventar requisitos; consultar al supervisor si hay dudas).
5. **Rendimiento del ranking** en SQLite con 100 usuarios: validar en el Sprint 12.5 antes del despliegue real.
