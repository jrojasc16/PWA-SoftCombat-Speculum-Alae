/* Service worker (Sprint 7.6): app-shell + caché en tiempo de ejecución.
 *
 * - Precaché del app-shell: portada, ranking público y estáticos, para que la
 *   PWA abra sin conexión.
 * - Las lecturas públicas ("/" y "/ranking") usan estrategia
 *   «red primero, caché de respaldo» (network-first), así siempre se ve el
 *   ranking más fresco posible y, sin conexión, la última versión cacheada
 *   (lectura offline del ranking).
 * - Nunca se cachean POST/confirmaciones ni páginas de sesión: sería un riesgo
 *   de datos (el historial y los pendientes dependen de la sesión).
 */

const CACHE_SHELL = "sa-shell-v1";
const CACHE_LECTURA = "sa-lectura-v1";

const APP_SHELL = [
  "/",
  "/ranking",
  "/static/css/estilos.css",
  "/static/manifest.json",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches
      .open(CACHE_SHELL)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((claves) =>
        Promise.all(
          claves
            .filter((clave) => ![CACHE_SHELL, CACHE_LECTURA].includes(clave))
            .map((clave) => caches.delete(clave))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  if (peticion.method !== "GET") return;

  const url = new URL(peticion.url);
  if (url.origin !== self.location.origin) return;

  // Nunca cachear recursos de sesión o de escritura.
  if (
    url.pathname.startsWith("/me") ||
    url.pathname.startsWith("/combats") ||
    url.pathname.startsWith("/admin") ||
    url.pathname.startsWith("/auth") ||
    url.pathname.startsWith("/pendientes")
  ) {
    return;
  }

  // Navegaciones y lecturas públicas: red primero, caché de respaldo.
  if (
    peticion.mode === "navigate" ||
    url.pathname === "/api/ranking" ||
    url.pathname.startsWith("/static/")
  ) {
    evento.respondWith(
      fetch(peticion)
        .then((respuesta) => {
          if (respuesta.ok) {
            const copia = respuesta.clone();
            caches.open(CACHE_LECTURA).then((cache) => cache.put(peticion, copia));
          }
          return respuesta;
        })
        .catch(() =>
          caches.match(peticion).then((guardada) => guardada || caches.match("/ranking"))
        )
    );
    return;
  }

  // Resto de GETs: caché primero, red de respaldo.
  evento.respondWith(
    caches.match(peticion).then((guardada) => guardada || fetch(peticion))
  );
});
