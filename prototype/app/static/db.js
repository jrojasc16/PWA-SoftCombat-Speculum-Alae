/* IndexedDB: reservado para la cola outbox de reportes offline
 * (FIFO, backoff, clave de idempotencia) — prevista en un sprint posterior.
 * De momento la PWA solo lee offline (app-shell del service worker); el
 * reporte offline se construirá sobre la clave `client_request_id` de
 * POST /combats (Sprint 4).
 */
