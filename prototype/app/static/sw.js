/* Service worker (Sprint 8.2): app-shell + runtime cache con marca de tiempo.
 *
 * - Precaché del app-shell: portada, ranking público, CSS, JS común, manifest e
 *   iconos, para que la PWA abra sin conexión.
 * - Lecturas "stale-while-revalidate" (SWR): el ranking público (`/api/ranking`)
 *   y el historial propio (`/me/history`). Se responde de inmediato con la copia
 *   cacheada (rápido y tolerante a cortes de red) y en segundo plano se
 *   revalida contra el servidor; cuando llega la versión fresca se notifica a
 *   las pestañas abiertas para que actualicen la vista.
 * - Marca de tiempo: cada copia guardada se almacena con la cabecera
 *   `X-SW-Cache-Time` (ISO 8601), que la UI usa para mostrar "datos de las
 *   HH:MM" y para saber si lo que ve el usuario viene de la caché.
 * - Nunca se cachean POST/confirmaciones ni páginas de sesión sensible
 *   (`/combats`, `/admin`, `/auth`, `/pendientes`, `/me`): sería un riesgo de
 *   datos (dependen de la sesión y de la identidad del usuario).
 */

const CACHE_SHELL = "sa-shell-v2";
const CACHE_LECTURA = "sa-lectura-v2";

const CABECERA_MARCA = "X-SW-Cache-Time";

const APP_SHELL = [
  "/",
  "/ranking",
  "/offline",
  "/static/css/estilos.css",
  "/static/js/app.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

/* Lecturas públicas y propias con estrategia stale-while-revalidate. */
const RUTAS_SWR = ["/api/ranking", "/me/history"];

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

  // Lecturas con marca de tiempo: respuesta inmediata desde la caché y
  // revalidación en segundo plano.
  if (esRutaSWR(url.pathname)) {
    evento.respondWith(responderConSWR(peticion));
    return;
  }

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

  // Navegaciones y estáticos: red primero, caché de respaldo. Solo el
  // app-shell se guarda al navegar: las páginas con datos de sesión
  // (/historial, /reportar, …) jamás se cachean, igual que sus APIs.
  if (peticion.mode === "navigate" || url.pathname.startsWith("/static/")) {
    const esNavegacion = peticion.mode === "navigate";
    const guardable = !esNavegacion || APP_SHELL.includes(url.pathname);
    evento.respondWith(
      fetch(peticion)
        .then((respuesta) => {
          if (respuesta.ok && guardable) {
            const copia = respuesta.clone();
            caches.open(CACHE_LECTURA).then((cache) => cache.put(peticion, copia));
          }
          return respuesta;
        })
        .catch(() =>
          caches.match(peticion).then((guardada) => guardada || caches.match("/offline"))
        )
    );
    return;
  }

  // Resto de GETs: caché primero, red de respaldo.
  evento.respondWith(
    caches.match(peticion).then((guardada) => guardada || fetch(peticion))
  );
});

/* Mensajes desde la UI: consulta de marcas de tiempo y purga de datos propios. */
self.addEventListener("message", (evento) => {
  const datos = evento.data || {};

  if (datos.tipo === "sa-limpiar-cache") {
    // Al cerrar sesión, el historial propio cacheado deja de ser válido.
    evento.waitUntil(limpiarCachePersonal());
    return;
  }

  if (datos.tipo === "sa-datos-cache") {
    // La página sin conexión pide el contenido JSON de las copias guardadas.
    evento.waitUntil(
      datosCacheados().then((datos) => {
        if (evento.ports && evento.ports[0]) {
          evento.ports[0].postMessage({ tipo: "sa-datos-cache", datos });
        } else if (evento.source) {
          evento.source.postMessage({ tipo: "sa-datos-cache", datos });
        }
      })
    );
    return;
  }

  if (datos.tipo !== "sa-estado-cache") return;
  evento.waitUntil(
    marcasDeCache().then((marcas) => {
      if (evento.ports && evento.ports[0]) {
        evento.ports[0].postMessage(marcas);
      } else if (evento.source) {
        evento.source.postMessage({ tipo: "sa-estado-cache", marcas });
      }
    })
  );
});

/** Elimina de la caché las lecturas propias de la sesión (/me/...). */
async function limpiarCachePersonal() {
  const cache = await caches.open(CACHE_LECTURA);
  const claves = await cache.keys();
  await Promise.all(
    claves
      .filter((peticion) => new URL(peticion.url).pathname.startsWith("/me"))
      .map((peticion) => cache.delete(peticion))
  );
}

/** Contenido JSON de las copias guardadas de las lecturas SWR. */
async function datosCacheados() {
  const cache = await caches.open(CACHE_LECTURA);
  const datos = {};
  for (const ruta of RUTAS_SWR) {
    const guardada = await cache.match(ruta);
    if (!guardada) continue;
    try {
      datos[ruta] = await guardada.clone().json();
    } catch (error) {
      // La copia no es JSON válido: se ignora.
    }
  }
  return datos;
}

/** Indica si la ruta usa la estrategia stale-while-revalidate. */
function esRutaSWR(ruta) {
  return RUTAS_SWR.includes(ruta);
}

/** Marca de tiempo de las entradas cacheadas de las rutas SWR. */
async function marcasDeCache() {
  const cache = await caches.open(CACHE_LECTURA);
  const marcas = {};
  for (const ruta of RUTAS_SWR) {
    const guardada = await cache.match(ruta);
    if (!guardada) continue;
    marcas[ruta] = guardada.headers.get(CABECERA_MARCA);
  }
  return marcas;
}

/**
 * Responde con la copia cacheada (marca de tiempo visible para la UI) y
 * revalida en segundo plano; si no hay copia, espera a la red.
 */
async function responderConSWR(peticion) {
  const cache = await caches.open(CACHE_LECTURA);
  const guardada = await cache.match(peticion);

  const desdeRed = fetch(peticion)
    .then(async (respuesta) => {
      if (!respuesta.ok) return respuesta;
      const marcada = await guardarConMarca(cache, peticion, respuesta);
      await avisarActualizacion(peticion.url);
      return marcada;
    })
    .catch(() => null);

  if (guardada) {
    // La revalidación sigue en segundo plano; no bloquea la respuesta.
    desdeRed.catch(() => null);
    return guardada;
  }

  const respuesta = await desdeRed;
  if (respuesta) return respuesta;

  return new Response(
    JSON.stringify({ error: "Sin conexión y sin copia cacheada de esta lectura." }),
    {
      status: 503,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    }
  );
}

/** Guarda la respuesta en la caché añadiendo la marca de tiempo de guardado. */
async function guardarConMarca(cache, peticion, respuesta) {
  const cuerpo = await respuesta.clone().arrayBuffer();
  const cabeceras = new Headers(respuesta.headers);
  cabeceras.set(CABECERA_MARCA, new Date().toISOString());
  const marcada = new Response(cuerpo, {
    status: respuesta.status,
    statusText: respuesta.statusText,
    headers: cabeceras,
  });
  await cache.put(peticion, marcada.clone());
  return marcada;
}

/** Avisa a las pestañas abiertas que hay una versión fresca en la caché. */
async function avisarActualizacion(url) {
  const clientes = await self.clients.matchAll({ includeUncontrolled: true });
  for (const cliente of clientes) {
    cliente.postMessage({ tipo: "sa-cache-actualizada", url });
  }
}
