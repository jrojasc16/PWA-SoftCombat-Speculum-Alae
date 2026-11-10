# Verificación de instalabilidad y compatibilidad de la PWA (Sprint 8.4)

**Alcance:** RNF005 — «Chrome/Firefox/Edge/Safari (2 últimas versiones); PWA instalable en Android y escritorio».
**Fecha:** 2026-11-09 · **Rama:** `desarrollo-sprint-7` · **Commit:** `Sprint 8, tarea 8.4`

---

## 1. Verificación automática (reproducible en la CI)

Se añadió el verificador `scripts/verificar_pwa.py`, que descarga la app en
marcha y comprueba **todos** los criterios de instalabilidad que exigen los
navegadores. No depende de herramientas externas (solo biblioteca estándar).

```bash
# 1) Levantar la app
cd prototype && ../venv/bin/python run.py

# 2) En otra terminal, verificar
venv/bin/python scripts/verificar_pwa.py --url http://127.0.0.1:5000
```

Salida real obtenida el 2026-11-09 contra `http://127.0.0.1:5000`:

```
[ OK ] Manifest descargable: HTTP 200 en /static/manifest.json
[ OK ] Manifest con JSON válido: JSON correcto
[ OK ] Manifest con «name»: Speculum-Alae Ranking
[ OK ] Manifest con «short_name»: SA Ranking
[ OK ] Manifest con «start_url»: /ranking
[ OK ] Manifest con «scope»: /
[ OK ] Manifest con display standalone: display='standalone'
[ OK ] Manifest con «theme_color»: #550a56
[ OK ] Manifest con «background_color»: #e3e3e3
[ OK ] Manifest con iconos de 192 y 512 px: sizes=['192x192', '512x512']
[ OK ] Icono /static/icons/icon-192.png: HTTP 200, tipo image/png, dimensiones (192, 192)
[ OK ] Icono /static/icons/icon-512.png: HTTP 200, tipo image/png, dimensiones (512, 512)
[ OK ] Layout enlazado al manifest: HTTP 200, rel=manifest: True
[ OK ] Layout con theme-color: meta theme-color presente
[ OK ] Página start_url: /ranking → HTTP 200
[ OK ] Página respaldo sin conexión: /offline → HTTP 200
[ OK ] Service worker descargable: HTTP 200
[ OK ] Service worker con manejador fetch: registra el evento fetch
[ OK ] Service worker con alcance en la raíz: Service-Worker-Allowed='/'
[INFO] Origen seguro para instalar: localhost

Todos los criterios de instalabilidad se cumplen.
```

La misma verificación corre en la CI: `prototype/tests/test_pwa_instalabilidad.py`
levanta la app en un puerto efímero y ejecuta el verificador contra ella
(incluye un caso negativo con un manifest incompleto).

## 2. Criterios verificados y su base técnica

| Criterio | Implementación | Archivo |
|---|---|---|
| Manifest completo y válido | `name`, `short_name`, `description`, `lang`, `dir`, `id`, `start_url`, `scope`, `display`, `display_override`, `orientation`, `categories`, `theme_color`, `background_color`, iconos | `prototype/app/static/manifest.json` |
| Iconos instalables | PNG 192×192 y 512×512, `purpose: any maskable`, zona segura respetada | `prototype/app/static/icons/`, `scripts/generar_iconos_pwa.py` |
| Iconos referenciados | `rel="icon"` y `rel="apple-touch-icon"` + `meta theme-color` | `prototype/app/templates/base.html` |
| Service worker con alcance raíz | Cabecera `Service-Worker-Allowed: /` en `/static/sw.js` | `prototype/app/__init__.py` |
| Pantalla de inicio sin conexión | Ruta pública `/offline` servida como fallback de navegación | `prototype/app/modules/ui/routes.py`, `prototype/app/templates/offline.html` |
| Origen seguro | `ProductionConfig` exige `SECRET_KEY` y cookies `Secure`; en producción el sitio se sirve por HTTPS (RNF001) | `prototype/app/config.py` |

## 3. Verificación manual con Lighthouse (pendiente de navegador real)

El entorno de desarrollo del proyecto **no tiene navegador instalado**, por lo
que no se pudo ejecutar Lighthouse aquí. El procedimiento a seguir en el
equipo (Chrome o Edge, con la app servida en `localhost` o en HTTPS) es:

1. Levantar la app y abrir `http://127.0.0.1:5000/ranking`.
2. En Chrome: **DevTools → Lighthouse → categoría *Progressive Web App* → Generate report**.
3. Comprobar que en *Installability* aparecen los cuatro puntos:
   - *Has a web app manifest with a name, short name, start URL, and display* ✔
   - *Has an icon with 192×192 and 512×512 pixels* ✔
   - *Has a service worker with a fetch handler* ✔
   - *Is served over HTTPS* (en `localhost` Lighthouse lo considera seguro) ✔
4. Guardar el reporte JSON como evidencia:
   `lighthouse http://127.0.0.1:5000/ranking --only-categories=pwa --output=json --output-path=evidencia/lighthouse-pwa.json`
5. Repetir en **Firefox**, **Edge** y **Safari** (en Safari la instalación se
   valida con *Compartir → Añadir a pantalla de inicio*; el criterio equivalente
   es que la app se abra sin barra de navegador y mantenga el service worker).
6. En **Android** (Chrome/Edge): menú ⋮ → **Instalar aplicación**; verificar que
   aparece el icono propio y que la app arranca en modo `standalone`.
7. En **escritorio** (Chrome/Edge): el icono de instalación aparece en la barra
   de direcciones; en Windows y macOS la app se abre en ventana propia.

**Compatibilidad declarada (RNF005):** Chrome, Firefox, Edge y Safari, en sus
dos últimas versiones, usando solo APIs estándar (Service Worker, Cache API,
IndexedDB —esta última a partir del Sprint 9—, `navigator.onLine`,
`MessageChannel`).

## 4. Limitaciones conocidas

- **Safari iOS** no permite instalar desde el sitio antes de iOS 16.4: en
  versiones anteriores la PWA funciona, pero solo como pestaña de navegador
  (la lectura offline y el manifest siguen siendo válidos).
- En **Firefox** la instalación automática no existe: se usa *Instalar* desde el
  menú de la barra de direcciones o la instalación manual desde el sistema.
- El service worker **no** cachea datos de sesión sensibles (`/combats`,
  `/admin`, `/auth`, `/pendientes`); el historial propio cacheado se purga al
  cerrar sesión (`sa-limpiar-cache`).
