# Manual de operación — Speculum-Alae (Sprint 13.7)

Guía de **operación y mantenimiento** de la instancia desplegada del prototipo
(PWA + backend Flask/SQLite en PythonAnywhere). Complementa la guía de
despliegue (`documentation/DEPLOY_PYTHONANYWHERE.md`), que describe **cómo
publicar** la aplicación; este documento describe **cómo mantenerla viva**.

- **Audiencia:** equipo del proyecto y quien quede a cargo tras el cierre del curso.
- **Alcance:** renovación de cuenta, respaldos/restauración de SQLite,
  actualizaciones, rotación de secretos, recálculo del ranking, monitoreo de
  logs y respuesta a incidentes, con los límites del plan gratuito en mente.
- **Frecuencia de revisión:** cada inicio de sprint (o cada mes, lo que ocurra antes).

---

## 1. Accesos y secretos

| Recurso | Dónde vive | Regla |
|---|---|---|
| Cuenta PythonAnywhere | cuenta **universitaria/compartida** del equipo (no personal) | credenciales en el gestor de contraseñas del equipo, nunca en el repo |
| Repositorio | `origin` GitHub `jrojasc16/PWA-SoftCombat-Speculum-Alae` | el push lo hace un integrante con credenciales |
| `SECRET_KEY` de producción | `prototype/.env` en el servidor (`chmod 600`) | **nunca** se commitea (`.env` está en `.gitignore`) |
| Base de datos | `prototype/instance/app.db` (SQLite, WAL) | **nunca** se sube al repositorio (`*.db` en `.gitignore`) |
| Panel de administración | usuario con rol `admin`/`super_admin` en `/admin` | alta de administradores solo por un `super_admin` |

> Si se filtra `.env`, rotar la `SECRET_KEY` (§4.5) invalida las sesiones firmadas:
> los usuarios simplemente vuelven a iniciar sesión.

---

## 2. Calendario de operación

| Periodicidad | Tarea | Sección |
|---|---|---|
| **Diario** (durante uso activo) | Revisar `/health` y el *Error log* si hay reportes de fallos | §5 |
| **Semanal** | Revisar conflictos pendientes en `/admin/panel/combates`; confirmar que el ranking cuadra | §4.6 |
| **Mensual** | **Renovar la web app** (evita el 404 por expiración) | §4.1 |
| **Mensual** | **Respaldo de SQLite** + copia fuera del servidor | §4.2 |
| **Por despliegue** | Respaldo → `git pull` → migraciones → *Reload* | §4.4 |
| **Al cierre del curso** | Respaldo final + descarga + acta | §4.2 / §7 |

---

## 3. Herramientas de operación

- **Consola Bash** de PythonAnywhere (*Consoles*) con el venv activado:
  `workon sa-venv` y `cd ~/PWA-SoftCombat-Speculum-Alae`.
- **Pestaña Web** → *Reload* (recarga la app), *run until* (renovación) y
  *Error log* / *Server log* (diagnóstico).
- **Panel de administración** (`/admin`) para la operación de negocio.
- **Scripts del repo** (§4.6–§4.7) para tareas masivas reproducibles.

---

## 4. Rutinas

### 4.1 Renovación mensual de la cuenta (crítico)

Las cuentas gratuitas tienen la web app **activa 1 mes**; si no se renueva
dentro del plazo, la app **expira** y deja de responder (404 de PythonAnywhere).
PA avisa por correo con antelación.

1. Entrar a la pestaña **Web** y pulsar el botón de **renovación** («run
   until»), que extiende la fecha.
2. Comprobar que `https://<usuario>.pythonanywhere.com/health` responde
   `{"env":"production","status":"ok"}`.
3. Anotar la nueva fecha de vencimiento en la bitácora (§9) y en el calendario
   del equipo (recordatorio el **mismo día del despliegue** de cada mes).

### 4.2 Respaldo de SQLite (mensual y antes de cada despliegue)

El plan gratuito **no** tiene tareas programadas, así que el respaldo es manual.
Se usa la API `backup` de `sqlite3`, segura con el modo WAL:

```bash
workon sa-venv
cd ~/PWA-SoftCombat-Speculum-Alae
python - <<'EOF'
import datetime, sqlite3
hoy = datetime.date.today().isoformat()
origen = sqlite3.connect("prototype/instance/app.db")
destino = sqlite3.connect(f"respaldo-app-{hoy}.db")
origen.backup(destino)
destino.close(); origen.close()
print(f"respaldo-app-{hoy}.db listo")
EOF
```

Luego **descargar** el archivo por la pestaña *Files* y guardarlo **fuera del
servidor** (un archivo dentro del mismo disco no protege contra el borrado
accidental de la cuenta). Conservar al menos los 3 últimos respaldos.

### 4.3 Restauración desde un respaldo

```bash
workon sa-venv
cd ~/PWA-SoftCombat-Speculum-Alae
# Detener la app primero: pestaña Web → (no hay "stop"; basta no recibir tráfico)
cp prototype/instance/app.db prototype/instance/app.db.bak-$(date +%F)   # conservar el actual
cp ~/respaldo-app-YYYY-MM-DD.db prototype/instance/app.db
# Verificar integridad y arranque
python -c "import sqlite3; c=sqlite3.connect('prototype/instance/app.db'); print(c.execute('pragma integrity_check').fetchone())"
```

Pestaña Web → **Reload** y repetir el smoke test (§5). Si algo falla, restaurar
el `app.db.bak-*` conservado.

### 4.4 Actualización de la aplicación

```bash
workon sa-venv
cd ~/PWA-SoftCombat-Speculum-Alae
python - <<'EOF'   # respaldo previo (§4.2)
import datetime, sqlite3
hoy=datetime.date.today().isoformat()
o=sqlite3.connect("prototype/instance/app.db"); d=sqlite3.connect(f"respaldo-app-{hoy}.db")
o.backup(d); d.close(); o.close()
EOF
git pull
pip install -r prototype/requirements.txt          # si cambió requirements.txt
cd prototype && flask --app wsgi.py db upgrade     # si hubo migraciones
# Pestaña Web → Reload
```

Tras recargar: smoke test (§5). Ante un 500, revisar el *Error log*; si el error
es `RuntimeError: SECRET_KEY no definida`, el `.env` no se cargó (ver
`DEPLOY_PYTHONANYWHERE.md` §10).

### 4.5 Rotación de la `SECRET_KEY`

1. Generar una clave nueva:
   `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Editar `prototype/.env` (solo `export SECRET_KEY=…`) y `chmod 600`.
3. Pestaña Web → **Reload**. Efecto: se invalidan todas las sesiones firmadas
   (todos vuelven a iniciar sesión); los datos **no** se ven afectados.

### 4.6 Recálculo del ranking (operación de negocio)

El ranking se recalcula **on-write** al confirmar cada combate; el recálculo
manual solo se necesita si hubo ediciones admin o sospecha de inconsistencia.

- **Desde el panel:** `/admin` → «Recalcular ranking» (`window.confirm` previo);
  el resultado muestra **N combate(s) reprocesados**.
- **Por API:** `POST /admin/ranking/recalculate` (sesión de `admin`/`super_admin`).
- Es **idempotente**: reconstruye los índices desde los combates terminales sin
  duplicar historial. Tras ejecutarlo, verificar en `/ranking` que las posiciones
  y los puntos cuadran con los combates confirmados.

### 4.7 Semilla y reinicio de datos (entornos de prueba)

```bash
cd ~/PWA-SoftCombat-Speculum-Alae/prototype
../venv/bin/python ../scripts/semillar_datos.py --usuarios 100 --combates 200 --seed 1
# --reset para vaciar antes de sembrar; NUNCA usar --reset en producción con datos reales
```

### 4.8 Altas y cambios de usuarios (operación de negocio)

Desde `/admin/panel/usuarios` (rol `admin`/`super_admin`, misma comunidad):
activar/desactivar usuarios y cambiar roles. Reglas del sistema: nadie
desactiva ni cambia su propio rol; solo un `super_admin` concede o retira
`super_admin`. Cada edición de combate deja traza en la **bitácora de auditoría**.

---

## 5. Monitoreo y señales de salud

- **`GET /health`** → `{"env":"production","status":"ok"}`. Es el chequeo más
  rápido de que la app responde.
- **`GET /api/ranking`** → tabla pública; mide también el rendimiento (RNF002:
  p95 < 500 ms con 100 usuarios, ya validado en `documentation/CARGA_API_RANKING.md`).
- **CPU diario (100 s/día):** visible en la pestaña *Consoles*/*Web*. Un pico
  suele venir de sesiones de consola largas o scripts, no del tráfico web.
- **Logs:** *Web → Error log* (traza de las peticiones fallidas) y *Server log*.
  Revisarlos ante cualquier 500 reportado por la comunidad.
- **PWA:** si el ranking offline deja de actualizarse, comprobar que **no** se
  añadieron *static files* en la pestaña Web (rompería `Service-Worker-Allowed`).

---

## 6. Límites del plan gratuito y cuándo escalar

| recurso | límite gratuito | riesgo / mitigación |
|---|---|---|
| Web apps | 1 (1 worker) | suficiente para una comunidad; sin balanceo |
| Espera de arranque | la app se «duerme» y la primera petición tarda | normal; avisar a los usuarios |
| Expiración | 1 mes | **renovar mensualmente** (§4.1) |
| CPU | 100 s/día (consola/tareas) | el tráfico web no se cobra; evitar scripts pesados en consola |
| Disco | 512 MiB | SQLite de MBs; vigilar los respaldos acumulados |
| MySQL / cron | **no** disponibles | SQLite + respaldos manuales (§4.2) |
| Dominio propio | solo de pago | usar el subdominio `*.pythonanywhere.com` |

**Escalar a plan de pago** si: hace falta dominio propio, más de 1 worker
(tráfico concurrente alto), tareas programadas para respaldos automáticos, o
más de 512 MiB de datos.

---

## 7. Respuesta a incidentes

| síntoma | causa probable | acción |
|---|---|---|
| La web devuelve 404 de PA | app **caducada** (1 mes) | Renovar en la pestaña Web (§4.1) |
| `RuntimeError: SECRET_KEY no definida` | `.env` ausente o mal cargado | Revisar `prototype/.env` y el WSGI; *Reload* |
| `502` / «Something went wrong» | error de import o de arranque | *Error log*; corregir y *Reload* |
| Ranking descuadrado | edición admin sin recálculo | Recalcular (§4.6) |
| PWA sin caché offline | *static files* mapeados en PA | Borrar el mapeo y *Reload* |
| `database is locked` | dos procesos escribiendo el `.db` | Usar solo la web app (1 worker); no escribir desde consolas |
| Datos corruptos / pérdida | fallo del `.db` | Restaurar el último respaldo (§4.3) |
| Cuenta comprometida | filtración de credenciales | Rotar `SECRET_KEY` (§4.5), cambiar la contraseña de PA y revisar roles |

Escalamiento: primero el equipo del proyecto; si el problema es de la
plataforma, los **foros de la comunidad** de PythonAnywhere (el plan gratuito
no tiene soporte directo).

---

## 8. Checklist de fin de curso (entrega)

- [ ] Respaldo final de SQLite descargado y guardado fuera del servidor (§4.2).
- [ ] `prototype/.env` documentado en el gestor del equipo (sin exponerlo).
- [ ] Fecha de vencimiento de la web app anotada + responsable de renovación.
- [ ] Bitácora de operaciones (§9) cerrada y adjunta al acta de cierre.
- [ ] Confirmado que ni `.env` ni `*.db` entraron al repositorio.

---

## 9. Bitácora de operaciones (plantilla)

| fecha | tarea | resultado | responsable |
|---|---|---|---|
| | | | |
| | | | |
