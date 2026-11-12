# Revisión de seguridad — Sprint 12, tarea 12.6

- **Fecha:** 2026-11-11
- **Alcance:** los 4 puntos fijados en el plan — bcrypt costo 12 efectivo, cookies `Secure`/`HttpOnly`, HTTPS forzado en producción y ausencia de datos sensibles en respuestas públicas (RNF001).
- **Pruebas nuevas:** `prototype/tests/test_seguridad.py` (9 tests). Suite completa: **412 tests en verde**, cobertura `app.modules.ranking` = 100 %.
- **Conclusión global: ✅ los 4 puntos CUMPLEN** (3 hallazgos menores anotados al final, sin acción requerida en este sprint).

---

## 1. bcrypt con costo 12 efectivo ✅

| evidencia | ubicación |
|---|---|
| `BCRYPT_LOG_ROUNDS = 12` (base; producción lo hereda) | `prototype/app/config.py:28` |
| Costo 4 solo en `TestingConfig` (velocidad) | `prototype/app/config.py:53` |
| El servicio lee la config en cada hash: `generate_password_hash(password, rounds=current_app.config["BCRYPT_LOG_ROUNDS"])` | `prototype/app/modules/iam/services.py:64-66` |
| Login verifica con el mismo bcrypt | `prototype/app/modules/iam/services.py:90` |

- **Test existente:** `test_hash_bcrypt_costo_12_efectivo` (`tests/test_iam.py:71`) — config en 12 y hash verificable.
- **Test nuevo:** `test_bcrypt_costo_12_efectivo_al_registrar` — pisa la config a 12 (como en el despliegue) y comprueba el hash **real** generado por el servicio: prefijo `$2b$12$`, no igual a la contraseña, `check_password_hash` positivo y negativo.

## 2. Cookies de sesión `Secure` / `HttpOnly` ✅

| bandera | valor | dónde |
|---|---|---|
| `SESSION_COOKIE_HTTPONLY` | `True` en todos los entornos | `config.py:32` |
| `SESSION_COOKIE_SAMESITE` | `"Lax"` en todos los entornos | `config.py:33` |
| `SESSION_COOKIE_SECURE` | `False` en dev/testing (http local), **`True` en producción** | `config.py:34`, `config.py:61` |

- **Tests nuevos:** `test_cookie_de_sesion_httponly_y_samesite` (lee el `Set-Cookie` real del registro: contiene `HttpOnly` y `SameSite=Lax`) y `test_config_produccion_cookies_seguras` (banderas de `Config` y `ProductionConfig`).
- Efecto: `HttpOnly` → la cookie no es legible desde JavaScript (anti-XSS); `Secure` → el navegador solo la envía por HTTPS; `SameSite=Lax` → **mitigación CSRF**: el navegador no adjunta la cookie en POST cross-site.

## 3. HTTPS forzado en producción ✅ (3 capas)

**Capa 1 — aplicación.** `ProductionConfig.init_app` (`config.py:86-92`) registra un `before_request` que responde **308** a `https://` cuando (y solo cuando) hay evidencia positiva de HTTP por el proxy: cabecera `X-Forwarded-Proto: http` **y** URL `http://`. Diseño anti-bucle: si la cabecera no existe o dice `https`, no redirige — por tanto jamás se entra en bucle aunque la plataforma no use proxy. `308` (y no `301`) preserva método y cuerpo, necesario para los `POST` de la cola offline.

**Capa 2 — cookies.** `SESSION_COOKIE_SECURE = True` en producción: aunque algo intente servir por http, el navegador no transporta la sesión por ese canal.

**Capa 3 — plataforma.** El toggle **«Force HTTPS» de PythonAnywhere** (pestaña Web) redirige antes de que la petición llegue a la app, incluso cuando el proxy no envía `X-Forwarded-Proto`. Su propio blog explica por qué no se recomienda imponerlo solo en código (estáticos y `POST` no pasan por la app). **Es un paso obligatorio del despliegue (tarea 13.2)** y complementa —no duplica— la capa 1.

Además en `init_app` (`config.py:66-76`):

- `SECRET_KEY` **obligatoria** por variable de entorno: falta → `RuntimeError` (la app no arranca); presente → se fija en `app.config` **al inicializar** (no al importar), así el valor del entorno es el que aplica.
- `debug` apagado en producción (sin trazas ni consola interactiva en errores).

**Tests nuevos:** `test_produccion_sin_secret_key_no_arranca`, `test_produccion_con_secret_key_arranca_segura` (clave cargada, cookies `Secure`, `debug=False`) y `test_https_forzado_tras_proxy_sin_bucle` (GET/POST con cabecera `http` → 308 correcto; con `https` o sin cabecera → 200, sin bucle).

## 4. Sin datos sensibles en respuestas públicas ✅

| endpoint | auth | expone | test |
|---|---|---|---|
| `GET /api/ranking` | pública | `position`, `name`, `points`, `matches_played` (sin ids, correos ni hashes) | existente `test_api_ranking_sin_datos_sensibles` (`test_api_publica.py:67`) + nuevo `test_api_ranking_contrato_sin_campos_extra` (contrato cerrado) |
| `GET /health` | pública | solo `status`, `env` | nuevo `test_health_expone_solo_estado_y_entorno` |
| `GET /me/community` | sesión | id + nombre + rol para el formulario offline; sin correos | nuevo `test_directorio_comunidad_sin_correos_ni_hashes` |
| `/ranking` (HTML) | pública | solo nombres | existente `test_ranking_no_expone_correos` (`test_ui_ranking.py:72`) |
| errores de dominio | — | `{"error": mensaje}` sin trazas ni detalles internos | nuevo (400 de `/api/ranking`) + manejador global `app/shared/errors.py` |
| `POST /auth/login` con credenciales malas | — | mensaje genérico idéntico (sin oráculo de correos) | existente `test_login_incorrecto_mensaje_generico` (`test_iam.py:99`) |

Respuestas autenticadas (`/me`, `/me/history`, `/admin/users`) devuelven el perfil propio o el de la misma comunidad (RNF006) según rol — fuera del alcance de “públicas” y ya cubierto por sus tests de control de acceso.

---

## Observaciones menores (anotadas, sin acción en este sprint)

1. **CSRF por tokens no implementado (mitigación actual: `SameSite=Lax`).** No hay `Flask-WTF` en `requirements.txt`; `WTF_CSRF_ENABLED = False` (`config.py:55`) es un ajuste **residual sin efecto**. Con `SameSite=Lax` el navegador no adjunta la cookie de sesión en POST cross-site, y las APIs esperan JSON. Si en el futuro se aceptan formularios cross-site, añadir tokens CSRF.
2. **`409` en registro con correo ya existente** revela si un email está dado de alta. Es el comportamiento estándar de cualquier formulario de registro (decisión de UX del Sprint 2) y queda fuera de los 4 puntos; no se cambia sin decisión explícita.
3. **Sesión stateless (cookie firmada con `SECRET_KEY`).** No existe identificador de sesión en servidor que un atacante pueda “fijar”: la fijación de sesión clásica no aplica salvo que se filtre la `SECRET_KEY` o haya XSS (que `HttpOnly` limita). `login_user()` se llama sin `remember=True` → no hay cookie de recordar; la sesión muere al cerrar el navegador.

## Cómo reproducir la verificación

```bash
venv/bin/python -m pytest prototype/tests/test_seguridad.py -q   # 9 tests nuevos
venv/bin/python -m pytest prototype/tests -q                     # 412 en verde
```
