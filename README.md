# PWA-SoftCombat-Speculum-Alae
Aplicación web progresiva (PWA) para el seguimiento de desempeño deportivo (ranking Elo) de la comunidad de SoftCombat Speculum-Alae. Es un proyecto de clase para la asignatura Ingeniería de Software II.

## Estructura

- `prototype/` — monolito modular Flask + SQLite servido como PWA (HTML/CSS/JS vanilla), con el plugin de WordPress en `prototype/wordpress-plugin/`.
- `scripts/check.sh` — chequeo local: pytest + cobertura (≥70 % en `app.modules.ranking`, RNF007).

## API REST (OpenAPI)

El contrato completo de la API está en **[`prototype/docs/openapi.yaml`](prototype/docs/openapi.yaml)** (OpenAPI 3.0.3, RNF007): los 20 endpoints JSON de autenticación, combates, administración, historial y ranking público, con esquemas, códigos de error (400/401/403/404/409) y seguridad por cookie de sesión.

Para comprobar que el documento sigue siendo válido y que **no se ha desfasado del código** (cruza las rutas del spec con las reales de Flask, los enums con el dominio y la paginación con `shared/http.py`):

```bash
cd prototype
../venv/bin/python -m pytest tests/test_openapi.py -q
```

La validación usa el validador oficial de OpenAPI (`openapi-spec-validator`, incluido en `prototype/requirements.txt`).
