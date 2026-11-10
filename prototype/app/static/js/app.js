/* JS común (Sprint 8.3): registro del service worker, estado de conexión y
 * marca de tiempo de los datos mostrados ("datos de las HH:MM").
 *
 * La PWA funciona sin service worker: en ese caso no hay lectura offline y
 * el aviso se limita a informar del estado de la red.
 */
(function () {
  "use strict";

  /* Lecturas con copia en caché por página (tarea 8.2). */
  const RUTAS_CACHE = [
    { prefijo: "/ranking", ruta: "/api/ranking" },
    { prefijo: "/historial", ruta: "/me/history" },
  ];

  const banner = document.getElementById("aviso-offline");
  const marca = document.getElementById("marca-datos");
  const enlaceSalir = document.getElementById("enlace-salir");

  let registro = null;

  /** Ruta de API whose cached copy corresponds to the current page. */
  function rutaDeLectura() {
    const ruta = window.location.pathname;
    const encontrada = RUTAS_CACHE.find((item) => ruta.startsWith(item.prefijo));
    return encontrada ? encontrada.ruta : null;
  }

  /** Formats an ISO timestamp as HH:MM in the browser's locale. */
  function formatoHora(iso) {
    if (!iso) return null;
    const fecha = new Date(iso);
    if (isNaN(fecha.getTime())) return null;
    return fecha.toLocaleTimeString("es-CO", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  /** Pinta el banner con el estado de red y la hora de los datos. */
  function pintarEstado(marcaIso) {
    if (!banner) return;
    const sinRed = !navigator.onLine;
    const hora = formatoHora(marcaIso);
    banner.classList.toggle("aviso-offline--sin-red", sinRed);
    banner.classList.toggle("aviso-offline--con-datos", Boolean(hora));
    banner.hidden = false;
    if (sinRed) {
      banner.textContent = hora
        ? "Sin conexión — mostrando la copia guardada de las " + hora + "."
        : "Sin conexión — todavía no hay una copia guardada de esta lectura.";
    } else {
      banner.textContent = hora
        ? "En línea — última copia guardada: " + hora + "."
        : "En línea — los datos se muestran en tiempo real.";
    }
  }

  /** Muestra "Datos de las HH:MM" junto al contenido de la página. */
  function pintarMarca(marcaIso) {
    if (!marca) return;
    const hora = formatoHora(marcaIso);
    marca.textContent = hora ? "Datos de las " + hora : "";
    marca.hidden = !hora;
  }

  /**
   * Pide al servidor (a través del service worker) la lectura de la página:
   * con red actualiza la copia cacheada; sin red devuelve la copia guardada.
   */
  async function actualizarDatos() {
    const ruta = rutaDeLectura();
    if (!ruta) {
      pintarEstado(null);
      return;
    }
    try {
      const respuesta = await fetch(ruta, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      const iso = respuesta.headers.get("X-SW-Cache-Time");
      pintarMarca(iso);
      pintarEstado(iso);
    } catch (error) {
      pintarMarca(null);
      pintarEstado(null);
    }
  }

  /** Registra el service worker y avisa cuando hay una versión nueva. */
  function registrarServiceWorker() {
    if (!("serviceWorker" in navigator)) {
      pintarEstado(null);
      return;
    }
    window.addEventListener("load", () => {
      navigator.serviceWorker
        .register("/static/sw.js")
        .then((registroNuevo) => {
          registro = registroNuevo;
          registroNuevo.addEventListener("updatefound", () => {
            const instalando = registroNuevo.installing;
            if (!instalando) return;
            instalando.addEventListener("statechange", () => {
              if (instalando.state === "installed" && navigator.serviceWorker.controller) {
                if (banner) {
                  banner.classList.remove("aviso-offline--sin-red");
                  banner.textContent =
                    "Hay una versión nueva de la app: recarga para aplicarla.";
                  banner.hidden = false;
                }
              }
            });
          });
        })
        .catch(() => {
          // Sin service worker la app funciona igual: no hay lectura offline.
          pintarEstado(null);
        });
    });
  }

  /** Pide al service worker las marcas de tiempo de las copias cacheadas. */
  function pedirMarcas() {
    if (!navigator.serviceWorker || !navigator.serviceWorker.controller) return;
    const canal = new MessageChannel();
    canal.port1.onmessage = (evento) => {
      const marcas = (evento.data && evento.data.marcas) || {};
      const ruta = rutaDeLectura();
      const iso = ruta ? marcas[ruta] : null;
      if (iso) {
        pintarMarca(iso);
        pintarEstado(iso);
      }
    };
    navigator.serviceWorker.controller.postMessage(
      { tipo: "sa-estado-cache" },
      [canal.port2]
    );
  }

  /** Al cerrar sesión, purga del service worker las lecturas propias. */
  function purgarCacheAlSalir() {
    if (!enlaceSalir) return;
    enlaceSalir.addEventListener("click", () => {
      if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({ tipo: "sa-limpiar-cache" });
      }
      // El directorio local de la comunidad también es información personal.
      if (window.SAOutbox && window.SAOutbox.disponible()) {
        window.SAOutbox.borrarDirectorio().catch(() => null);
      }
    });
  }

  window.addEventListener("online", actualizarDatos);
  window.addEventListener("offline", () => pintarEstado(null));

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", (evento) => {
      const datos = evento.data || {};
      if (datos.tipo === "sa-cache-actualizada") {
        // El service worker ya tiene una versión fresca: se refleja la hora.
        pedirMarcas();
        actualizarDatos();
      }
    });
  }

  // Tras sincronizar la cola offline, los datos mostrados se refrescan.
  document.addEventListener("sa-outbox-cambio", (evento) => {
    const detalle = (evento && evento.detail) || {};
    if (detalle.tipo === "enviado" || detalle.tipo === "fin") {
      actualizarDatos();
    }
  });

  registrarServiceWorker();
  purgarCacheAlSalir();
  pedirMarcas();
  actualizarDatos();
})();
