# Guía de despliegue en PythonAnywhere — Speculum-Alae (Sprint 13.2)

- **Fecha:** 2026-11-11 · **Objetivo:** publicar el monolito `prototype/` en el
  plan **gratuito (Beginner)** de PythonAnywhere, con HTTPS obligatorio (RNF001).
- **Alcance:** variables de entorno (`SECRET_KEY`), `wsgi.py`, migraciones,
  pestaña Web, **Force HTTPS**, límites del plan gratuito y operación
  (renovación mensual y respaldos de SQLite).
- **Referencias oficiales:** [variables de entorno](https://help.pythonanywhere.com/pages/EnvironmentVariables),
  [plan gratuito](https://help.pythonanywhere.com/pages/FreeAccountsFeatures),
  [versiones de Python](https://help.pythonanywhere.com/pages/PythonVersions),
  [Flask en PA](https://help.pythonanywhere.com/pages/Flask),
  [Force HTTPS (blog)](https://blog.pythonanywhere.com/167),
  [cambios en cuentas gratuitas 2026 (blog)](https://blog.pythonanywhere.com/221).

> **Prerrequisito:** la rama `desarrollo-sprint-7` debe estar **empujada** al
> remoto (la hace el usuario: `git push -u origin desarrollo-sprint-7`), porque
> el código llega al servidor por `git clone`.

---

## 0. Qué ofrece el plan gratuito (enero 2026)

| recurso | límite |
|---|---|
| Aplicaciones web | **1** (1 worker; las peticiones en cola esperan) |
| URL | `https://<usuario>.pythonanywhere.com` (HTTPS incluido) |
| Expiración | **1 mes**: la app no usada caduca; se renueva con el botón de la pestaña Web (aviso por correo con antelación) |
| CPU | 100 segundos/día (consolas y tareas; el tráfico web no se cobra así) |
| Disco | 512 MiB |
| Consolas | 2 (Bash) |
| MySQL / tareas programadas | **no** en cuentas nuevas (desde 2026-01-15) |
| Dominio propio | solo en planes de pago |
| Soporte | comunitario (foros) |

Nuestro uso encaja: SQLite de pocos MB, tráfico de una comunidad y ninguna
llamada saliente desde el servidor.

---

## 1. Cuenta e imagen de sistema

1. Crear la cuenta gratuita en `pythonanywhere.com` (el equipo usa una cuenta
   **universitaria/compartida**, nunca una personal del docente).
2. Cuentas nuevas (imagen de sistema **innit**, desde 2025-03): Python
   **3.11, 3.12 y 3.13** disponibles. Si la cuenta es anterior: *Account →
   System image* para cambiar a la imagen actual.
3. Elegir **Python 3.12** (misma versión que la CI del repo) para el venv y
   para la web app.

## 2. Código en el servidor

Desde una **consola Bash** (pestaña *Consoles*):

```bash
cd ~
git clone https://github.com/jrojasc16/PWA-SoftCombat-Speculum-Alae.git
cd PWA-SoftCombat-Speculum-Alae
```

Alternativa sin git: subir un ZIP por la pestaña *Files* y descomprimirlo.

## 3. Virtualenv e instalación

```bash
# -p con la ruta completa evita el known issue de symlinks de la imagen innit
mkvirtualenv -p /usr/local/bin/python3.12 sa-venv
workon sa-venv
cd ~/PWA-SoftCombat-Speculum-Alae
pip install -r prototype/requirements.txt
```

## 4. Variables de entorno: `prototype/.env`

PythonAnywhere **no** inyecta variables en los procesos web por sí solo; su
guía oficial recomienda un archivo `.env` + `python-dotenv` (ya incluido en
`prototype/requirements.txt`). Los puntos de entrada `prototype/wsgi.py` y
`prototype/run.py` lo cargan automáticamente **antes** de crear la app, sin
pisar variables ya definidas en el entorno.

```bash
workon sa-venv
cd ~/PWA-SoftCombat-Speculum-Alae
python -c "import secrets; print(secrets.token_hex(32))"   # copiar la salida

cat > prototype/.env <<'EOF'
export FLASK_CONFIG=production
export SECRET_KEY=<pegar aquí la clave generada>
# export DATABASE_URL=   # opcional; por defecto sqlite://…/prototype/instance/app.db
EOF
chmod 600 prototype/.env
```

- `.env` está en `.gitignore` (raíz: patrón `.env`): **nunca se commitea**.
- La app **no arranca** sin `SECRET_KEY` en producción (`RuntimeError`
  intencionado — Sprint 12.6).
- Para comandos que **no** pasan por `wsgi.py`/`run.py` (p. ej. scripts
  sueltos), cargar el archivo en la consola:
  `set -a; source prototype/.env; set +a`.

## 5. Migraciones (tablas + seed de los 4 roles)

```bash
workon sa-venv
cd ~/PWA-SoftCombat-Speculum-Alae/prototype
flask --app wsgi.py db upgrade
```

`wsgi.py` carga el `.env` → entra en modo `production` y usa exactamente la
misma BD que servirá la web app (`prototype/instance/app.db`, modo WAL). Las
migraciones crean todas las tablas **y** siembran los roles fijos.

## 6. Pestaña *Web* → la aplicación

1. **Add a new web app** → **Manual configuration** → **Python 3.12**
   (la misma versión del venv; una web app Flask auto-generada no sirve:
   necesitamos la nuestra).
2. *Code*:
   - Source code / working directory:
     `/home/<usuario>/PWA-SoftCombat-Speculum-Alae/prototype`
   - Virtualenv: `/home/<usuario>/.virtualenvs/sa-venv`
3. **No agregar mapeos de archivos estáticos** (sección *Static files*):
   dejarla vacía. Flask debe servir `/static/` para emitir la cabecera
   `Service-Worker-Allowed: /` en `/static/sw.js`; si la sirve PythonAnywhere,
   esa cabecera se pierde y el **service worker deja de controlar la raíz**
   (la PWA dejaría de cachear el ranking).
4. **Archivo WSGI** (enlace *WSGI configuration file*, p. ej.
   `/var/www/<usuario>_pythonanywhere_com_wsgi.py`): reemplazar **todo** su
   contenido por:

   ```python
   import sys

   sys.path.insert(0, "/home/<usuario>/PWA-SoftCombat-Speculum-Alae/prototype")
   from wsgi import application  # prototype/wsgi.py: .env + create_app(production)
   ```

   Quien hace el trabajo pesado es `prototype/wsgi.py` (sys.path interno,
   `load_dotenv`, `create_app("production")` con cookies `Secure` y guard
   HTTPS). Así el archivo del sistema queda mínimo y el secreto **no** vive
   en él.
5. **Force HTTPS** (sección *Security* de la misma pestaña): activarlo y
   **Reload**. Es la **capa 3** de la revisión de seguridad (12.6): la
   infraestructura de PA redirige `http://` → `https://` antes de llegar al
   código — incluso para rutas con estáticos, que por eso **no** se mapean en
   el punto 3. La app añade además (capa 1) un 308 cuando el proxy reporta
   `X-Forwarded-Proto: http` y (capa 2) cookies `Secure`.
   Nota: su blog documenta que la redirección de plataforma **no se aplica a
   POST** (se perdería el cuerpo); con cookies `Secure`+`SameSite=Lax` esos
   POST sin sesión no autentican a nadie, y la navegación normal termina en
   `https://` de todos modos.
6. **Save** → **Reload** (siempre recargar tras tocar código, `.env` o WSGI).

## 7. Smoke test en producción

```text
https://<usuario>.pythonanywhere.com/health      → {"env":"production","status":"ok"}
https://<usuario>.pythonanywhere.com/ranking     → tabla pública (200)
https://<usuario>.pythonanywhere.com/login       → formulario (200)
```

Registro → reportar combate → dos confirmaciones → ranking actualizado. Ante
un 500: pestaña *Web → Error log* (y *Server error log*). Si el error es
`RuntimeError: SECRET_KEY no definida`, el `.env` no se está cargando
(comprobar rutas y que el WSGI apunta a `prototype/wsgi.py`).

El plugin de WordPress (`[ranking_table]`) debe apuntar en *Ajustes → Ranking
SA* a `https://<usuario>.pythonanywhere.com/api/ranking`.

## 8. Actualizaciones posteriores

```bash
workon sa-venv
cd ~/PWA-SoftCombat-Speculum-Alae
git pull
pip install -r prototype/requirements.txt    # si cambió requirements
cd prototype && flask --app wsgi.py db upgrade   # si hubo migraciones
# Web tab → Reload
```

## 9. Operación (plan gratuito)

- **Renovación mensual.** La pestaña *Web* muestra hasta qué fecha corre la
  app («run until»); hay que extenderla cada mes — si no, la app **expira a
  los 30 días sin usarse** y PA avisa por correo con antelación. Poner un
  recordario de calendario el mismo día del despliegue.
- **Respaldos de SQLite.** Las cuentas gratuitas **no** tienen tareas
  programadas: el respaldo se hace a mano desde una consola (la API `backup`
  de sqlite3 es segura con WAL):

  ```bash
  workon sa-venv
  cd ~/PWA-SoftCombat-Speculum-Alae
  python - <<'EOF'
  import datetime, sqlite3
  hoy = datetime.date.today()
  origen = sqlite3.connect("prototype/instance/app.db")
  destino = sqlite3.connect(f"respaldo-app-{hoy}.db")
  origen.backup(destino)
  destino.close(); origen.close()
  print(f"respaldo-app-{hoy}.db listo")
  EOF
  ```

  Descargar el archivo por la pestaña *Files* y conservarlo fuera del
  servidor (una copia dentro del mismo disco no protege contra borrado
  accidental de la cuenta). Repetir antes de cada despliegue grande y al
  cierre del curso. Los `*.db` están en `.gitignore`: **nunca** subir una BD
  al repositorio.
- **Límites operativos.** 512 MiB de disco (una BD de cientos de usuarios
  ocupa MBs); 100 CPU-s/día de consola; sin dominio propio ni MySQL en el
  plan gratuito; soporte solo por foros de la comunidad.
- **Credenciales.** `SECRET_KEY` solo en `.env` (chmod 600); las contraseñas
  de usuarios están hasheadas con bcrypt 12. Si se filtra `.env`, rotar la
  clave invalida las sesiones firmadas (los usuarios vuelven a entrar).

## 10. Solución de problemas

| síntoma | causa probable | arreglo |
|---|---|---|
| `RuntimeError: SECRET_KEY no definida` | falta `.env` o no lo carga el WSGI | §4 y §6.4; Reload |
| `ModuleNotFoundError: app` | el WSGI no insertó la ruta | §6.4 (ruta absoluta a `prototype/`) |
| PWA sin caché / SW sin controlar la raíz | mapeo de estáticos en PA quitó `Service-Worker-Allowed` | §6.3: borrar el mapeo y Reload |
| Página en verde con error de import en consola | venv con otra versión de Python | §3 y §6.1: mismas versiones |
| `sqlite3.OperationalError: database is locked` | más de un proceso escribiendo | usar siempre la app de la pestaña Web (1 worker) y no dejar consolas escribiendo a la vez |
| La web app caducó (404 de PA) | pasó 1 mes sin renovar | §9: botón de renovación en la pestaña Web |
