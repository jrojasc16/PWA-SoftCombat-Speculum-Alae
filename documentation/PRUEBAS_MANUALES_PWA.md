# Pruebas manuales de la PWA (Sprint 8.5)

**Objetivo:** documentar la verificación del modo offline de la app (RF14, mitad
de lectura) y de la instalación (RNF005), con pasos reproducibles por cualquier
integrante del equipo.
**Fecha:** 2026-11-09 · **Rama:** `desarrollo-sprint-7` · **Commit:** `Sprint 8, tarea 8.5`

---

## 0. Preparación

```bash
# Terminal 1 — app en desarrollo
cd prototype && ../venv/bin/python run.py

# Terminal 2 — comprobaciones de servidor (opcional, son las que sí se
# pueden automatizar sin navegador)
venv/bin/python scripts/verificar_pwa.py --url http://127.0.0.1:5000
```

Navegador: Chrome o Edge (herramientas de desarrollo completas), en
`http://127.0.0.1:5000/ranking`. Se recomienda abrir **DevTools → Application →
Service Workers** para observar el estado del SW y **Cache Storage** para ver las
copias guardadas.

> Las pruebas de navegador se ejecutan en el equipo del proyecto: el entorno de
> desarrollo usado para escribir este sprint no tiene navegador instalado. La
> columna *Estado* de cada caso queda para rellenarse con el resultado real y,
> si procede, la captura de pantalla.

---

## 1. Casos de prueba

### Caso 1 — Lectura offline del ranking público (caso clave del sprint)

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1.1 | Abrir `http://127.0.0.1:5000/ranking` con red | La tabla del ranking se muestra; el banner superior indica «En línea — los datos se muestran en tiempo real» |
| 1.2 | En DevTools → Application → Service Workers, comprobar el estado | El SW aparece **activated and running** |
| 1.3 | En DevTools → Application → Cache Storage, abrir `sa-lectura-v2` | Existe una entrada `http://127.0.0.1:5000/api/ranking` |
| 1.4 | Activar **Offline** en DevTools → Network (o poner el equipo en modo avión) | El banner cambia a «Sin conexión — mostrando la copia guardada de las HH:MM» |
| 1.5 | Recargar la página (`Ctrl+R`) | La página **carga** (viene del app-shell cacheado) y la tabla del ranking se muestra |
| 1.6 | Mirar el texto «Datos de las HH:MM» sobre la tabla | Coincide con la hora en que se guardó la copia |
| 1.7 | Desactivar Offline y recargar | El banner vuelve a «En línea» y los datos se actualizan |

### Caso 2 — La marca de tiempo refleja el guardado real

| Paso | Acción | Resultado esperado |
|---|---|---|
| 2.1 | Con red, recargar `/ranking` | La marca «Datos de las HH:MM» cambia a la hora actual (la respuesta de red se marca al guardarse) |
| 2.2 | Poner en modo avión y recargar | La marca **no** cambia: sigue mostrando la hora del último guardado |

### Caso 3 — Lectura offline del historial propio

| Paso | Acción | Resultado esperado |
|---|---|---|
| 3.1 | Iniciar sesión y abrir `/historial` con red | Se ve la tabla de combates con la variación de índice |
| 3.2 | En Cache Storage, comprobar `sa-lectura-v2` | Existe una entrada `http://127.0.0.1:5000/me/history` |
| 3.3 | Poner en modo avión y abrir `/historial` | La navegación falla en red: el SW sirve la página `/offline` |
| 3.4 | En `/offline`, comprobar las dos tablas | La tabla «Mi historial (copia guardada)» lista los combates con fecha, rival, resultado, estado e índice |

### Caso 4 — Página sin conexión y sus datos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 4.1 | Con red, visitar `/offline` | La página carga y muestra «Cargando la copia guardada…» y luego las tablas con los datos cacheados |
| 4.2 | Si no hay copia guardada | Cada tabla muestra «No hay copia guardada de esta lectura» (no hay error en consola) |

### Caso 5 — Los datos de sesión NO se cachean

| Paso | Acción | Resultado esperado |
|---|---|---|
| 5.1 | Con sesión iniciada, visitar `/pendientes` y `/reportar` | Funcionan con red |
| 5.2 | Poner en modo avión y recargar `/pendientes` | La navegación **no** muestra datos de pendientes cacheados: el SW sirve `/offline` (nunca una copia de `/pendientes`) |
| 5.3 | Revisar Cache Storage | No hay entradas de `/combats`, `/admin`, `/auth` ni `/pendientes` |

### Caso 6 — Purga de la caché personal al cerrar sesión

| Paso | Acción | Resultado esperado |
|---|---|---|
| 6.1 | Iniciar sesión, visitar `/historial` (se cachea `/me/history`) | Existe la entrada en `sa-lectura-v2` |
| 6.2 | Pulsar **Salir** en la navegación | La sesión se cierra y se vuelve al ranking |
| 6.3 | Revisar Cache Storage | La entrada `/me/history` **ya no está** (mensaje `sa-limpiar-cache` al service worker) |

### Caso 7 — Instalación (RNF005)

| Paso | Acción | Resultado esperado |
|---|---|---|
| 7.1 | Con red, abrir `/ranking` en Chrome/Edge | Aparece el icono de instalación en la barra de direcciones |
| 7.2 | Instalar la app | Se abre en ventana propia (`display: standalone`), con el icono propio y el color `#550a56` |
| 7.3 | Repetir en Android (Chrome) | Menú ⋮ → «Instalar aplicación»; la app se abre a pantalla completa |
| 7.4 | Medir con Lighthouse (categoría *Progressive Web App*) | *Installability* con los 4 puntos en verde (procedimiento en `documentation/PWA_VERIFICACION_INSTALABILIDAD.md`) |

### Caso 8 — Actualización de la app

| Paso | Acción | Resultado esperado |
|---|---|---|
| 8.1 | Con la app abierta, desplegar una versión nueva del SW | El banner superior avisa «Hay una versión nueva de la app: recarga para aplicarla» |
| 8.2 | Recargar | El SW nuevo toma el control (`skipWaiting` + `clients.claim`) y la app sigue funcionando |

---

## 2. Comprobaciones ya automatizadas (servidor, sin navegador)

Ejecutadas el 2026-11-09 contra la app en marcha:

| Comprobación | Resultado |
|---|---|
| `GET /static/manifest.json` | `200`, JSON válido con todos los campos de instalabilidad |
| `GET /static/icons/icon-192.png` / `icon-512.png` | `200`, `image/png`, 192×192 y 512×512 |
| `GET /` | `200` con `rel="manifest"`, `meta theme-color` e iconos |
| `GET /ranking` (`start_url`) | `200` |
| `GET /offline` | `200` |
| `GET /static/sw.js` | `200`, `Content-Type: text/javascript`, `Service-Worker-Allowed: /` |
| `GET /api/ranking` | `200`, `Cache-Control: public, max-age=300` |
| `scripts/verificar_pwa.py` | 19 criterios OK, 0 fallidos |
| `pytest` | 287 tests en verde, cobertura `app.modules.ranking` = 100 % |

## 3. Registro de la ejecución manual

| Caso | Fecha | Navegador | Resultado | Evidencia |
|---|---|---|---|---|
| 1 — Ranking offline | | | | |
| 2 — Marca de tiempo | | | | |
| 3 — Historial offline | | | | |
| 4 — Página `/offline` | | | | |
| 5 — Datos de sesión no cacheados | | | | |
| 6 — Purga al cerrar sesión | | | | |
| 7 — Instalación | | | | |
| 8 — Actualización del SW | | | | |

## 4. Incidencias detectadas y su tratamiento

| Incidencia | Tratamiento |
|---|---|
| La navegación offline a `/historial` no puede servir el HTML renderizado en servidor (depende de la sesión): se sirve `/offline`, que reconstruye la tabla desde la copia JSON cacheada de `/me/history` | Documentado en el Caso 3; es el límite de no cachear páginas de sesión |
| Safari en iOS < 16.4 no permite instalar la PWA | La app funciona como pestaña; limitación documentada en `documentation/PWA_VERIFICACION_INSTALABILIDAD.md` |
| Firefox no ofrece instalación automática | Se documenta la instalación manual en el Caso 7 |
