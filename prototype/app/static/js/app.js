/* JS común (Sprint 7.6): registro del service worker de la PWA.
 *
 * Se carga al final de todas las páginas (base.html). El registro es
 * best-effort: si el navegador no soporta service workers la app sigue
 * funcionando igual, solo sin lectura offline.
 */
(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/static/sw.js").catch(() => {
        // Sin service worker la app funciona igual: simplemente no hay
        // lectura offline ni app-shell cacheado.
      });
    });
  }
})();
