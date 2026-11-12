# Prototype — Speculum-Alae (Flask + SQLite + PWA)

Monolito modular que implementa el ranking Elo de la comunidad SoftCombat
Speculum-Alae: autenticación, reporte y confirmación de combates, recálculo
Elo on-write, ranking público cacheado, historial y panel de administración,
servido como PWA (HTML/CSS/JS vanilla + service worker). Python **3.11+**.

> Documentación del proyecto en la raíz: `README.md` (estructura y API),
> `documentation/` (informes, diagramas) y el contrato OpenAPI en
> [`docs/openapi.yaml`](docs/openapi.yaml).

## 1. Instalar

Desde la **raíz del repositorio**:

```bash
python3 -m venv venv
venv/bin/pip install -r prototype/requirements.txt
```

Las versiones están fijadas en `requirements.txt` (Flask 3, SQLAlchemy,
Flask-Login, Flask-Bcrypt, Flask-Migrate, pytest + cobertura y el validador
de OpenAPI). **Nota:** si el entorno usa Python 3.14 y pytest falla con
errores de `coverage`/`sqlalchemy _cy`, elimina los binarios Cython:

```bash
find venv -path '*sqlalchemy*' -name '*_cy.cpython-*.so' -delete
```

## 2. Migrar la base de datos

SQLite por defecto en `instance/app.db` (fuera del versionado; se crea y se
migra sola). Las migraciones son de Alembic/Flask-Migrate:

```bash
cd prototype
../venv/bin/flask --app run.py db upgrade
```

- Crea las tablas de los 6 módulos y siembra los **4 roles fijos**
  (`jugador`, `arbitro`, `admin`, `super_admin`) en la migración de datos.
- Usa siempre `--app run.py` (configuración de desarrollo) para migrar en
  local: `wsgi.py` arranca en `production` y exige `SECRET_KEY`.
- Para una migración nueva: `../venv/bin/flask --app run.py db migrate -m "…"`
  (los modelos se importan en `app/__init__.py`, Alembic los detecta).
- SQLite se activa en modo **WAL** automáticamente al conectar
  (`app/__init__.py`).

## 3. Correr

```bash
cd prototype
../venv/bin/python run.py        # servidor de desarrollo → http://127.0.0.1:5000
```

Comprobación rápida (debe responder `{"env": "development", "status": "ok"}`):

```bash
curl http://127.0.0.1:5000/health
```

En producción se usa `wsgi.py` (apuntado desde PythonAnywhere) con
`FLASK_CONFIG=production` y `SECRET_KEY` definida — ver la guía de
despliegue (`documentation/DEPLOY_PYTHONANYWHERE.md`, Sprint 13.2).

## 4. Testear

```bash
cd prototype
../venv/bin/python -m pytest -q        # suite completa (pytest.ini ya activa
                                       # la cobertura de app.modules.ranking)
```

Desde la raíz, con el umbral de RNF007 (cobertura ≥ 70 % en la lógica de
ranking; hoy 100 %):

```bash
./scripts/check.sh                     # pytest + cobertura con --cov-fail-under=70
./scripts/check.sh --con-navegador     # además: verificación E2E en navegador
                                       # (requiere la app en marcha en :5000)
```

Un archivo o test concreto: `../venv/bin/python -m pytest tests/test_e2e.py -q`.

## 5. Variables de entorno

| variable | entorno | descripción |
|---|---|---|
| `FLASK_CONFIG` | todos | `development` (por defecto), `testing` o `production`. |
| `SECRET_KEY` | **obligatoria en producción** | si falta, la app no arranca (`RuntimeError`). |
| `DATABASE_URL` | opcional | URL SQLAlchemy; por defecto SQLite en `instance/app.db`. |

Las variables pueden vivir en el archivo opcional **`prototype/.env`** (no
versionado; lo cargan `wsgi.py` y `run.py` con `python-dotenv` antes de crear
la app, sin pisar el entorno real). Es la forma recomendada en el despliegue
de producción — ver [`../documentation/DEPLOY_PYTHONANYWHERE.md`](../documentation/DEPLOY_PYTHONANYWHERE.md).

## 6. Semilla de datos de prueba (opcional)

Pobla la BD de desarrollo con usuarios y combates confirmados (para probar
el ranking a escala; ver `documentation/CARGA_API_RANKING.md`):

```bash
cd prototype && ../venv/bin/flask --app run.py db upgrade   # garantiza los roles
cd ..
venv/bin/python scripts/semillar_datos.py --reset           # 100 usuarios / 200 combates
```

Opciones: `--usuarios`, `--combates`, `--seed`, `--database-url`.

## 7. Estructura

```
prototype/
├── app/                  # Application Factory (create_app)
│   ├── config.py         # DevelopmentConfig / TestingConfig / ProductionConfig
│   ├── extensions.py     # db, login_manager, migrate, bcrypt
│   ├── modules/          # iam · combat · ranking · history · public_api · ui
│   │                     #   (routes → services → repositories → models)
│   ├── shared/           # decoradores, errores de dominio, http (paginación)
│   ├── static/           # CSS, JS vanilla, sw.js, manifest (PWA)
│   └── templates/        # Jinja2
├── migrations/           # Alembic (tablas + seed de roles)
├── docs/openapi.yaml     # contrato OpenAPI 3.0.3 (RNF007)
├── wordpress-plugin/     # shortcode [ranking_table] (lee GET /api/ranking)
├── tests/                # pytest (unit, contrato, e2e, seguridad, PWA)
├── run.py                # entrada de desarrollo
├── wsgi.py               # entrada de producción (PythonAnywhere)
├── pytest.ini            # testpaths + cobertura de app.modules.ranking
└── requirements.txt      # dependencias fijadas
```

- **PWA:** `sw.js` cachea el app-shell y lecturas públicas (ranking e
  historial) y deja una cola offline (`db.js`) para reportes con IndexedDB.
- **Ranking:** la fórmula Elo vive en `app/modules/ranking/domain/elo.py`
  (puro, sin dependencias) según el reglamento nacional de SoftCombat.
- **Roles:** los 4 roles son fijos; el rol se fija en la migración de datos.
