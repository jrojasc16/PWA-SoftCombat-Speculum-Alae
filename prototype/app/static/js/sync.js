/* Sincronización de la cola offline (Sprint 9.2).
 *
 * Drena la cola ``outbox`` de ``db.js`` cuando hay red:
 *
 * - Se dispara al abrir la app, en el evento ``online`` y tras encolar un
 *   reporte.
 * - Respeta el orden FIFO: si un envío falla con un error reintentable, se
 *   detiene el drenaje y programa el reintento con **backoff exponencial**
 *   (2 s, 4 s, 8 s… hasta 5 min).
 * - Cada reporte lleva su clave de idempotencia ``client_request_id``: si el
 *   servidor ya lo tenía registrado responde ``200`` y el reporte se marca
 *   como enviado (nunca como error).
 * - Notifica a la UI con el evento ``sa-outbox-cambio``.
 */
(function (global) {
  "use strict";

  const ESPERA_INICIAL_MS = 2000;
  const ESPERA_MAXIMA_MS = 300000;
  const RUTA_REPORTE = "/combats";
  const MAXIMO_ENVIADOS_GUARDADOS = 20;

  let sincronizando = false;
  let temporizador = null;

  /** Clave de idempotencia del reporte (UUID o equivalente). */
  function nuevaClave() {
    if (global.crypto && typeof global.crypto.randomUUID === "function") {
      return global.crypto.randomUUID();
    }
    return (
      "sa-" +
      Date.now().toString(16) +
      "-" +
      Math.random().toString(16).slice(2, 12)
    );
  }

  /** Espera del backoff exponencial para el número de intentos dado. */
  function esperaPara(intentos) {
    const espera = ESPERA_INICIAL_MS * Math.pow(2, Math.max(0, intentos - 1));
    return Math.min(espera, ESPERA_MAXIMA_MS);
  }

  /** Avisa a la UI de que la cola cambió. */
  function notificar(detalle) {
    if (typeof document === "undefined") return;
    document.dispatchEvent(
      new CustomEvent("sa-outbox-cambio", { detail: detalle || {} })
    );
  }

  /** Usuario de la sesión actual (o ``null`` si no hay sesión). */
  async function usuarioActual() {
    try {
      const respuesta = await fetch("/me", {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!respuesta.ok) return null;
      return await respuesta.json();
    } catch (error) {
      return null;
    }
  }

  /** Envía un reporte al servidor. */
  async function enviar(item) {
    const cuerpo = Object.assign({}, item.payload, {
      client_request_id: item.client_request_id,
    });
    let respuesta;
    try {
      respuesta = await fetch(RUTA_REPORTE, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(cuerpo),
      });
    } catch (error) {
      return { ok: false, reintentable: true, mensaje: "Sin conexión con el servidor." };
    }

    if (respuesta.ok) {
      let combate = null;
      try {
        combate = await respuesta.json();
      } catch (error) {
        combate = null;
      }
      return {
        ok: true,
        yaRegistrado: respuesta.status === 200,
        combate: combate,
      };
    }

    let datos = {};
    try {
      datos = await respuesta.json();
    } catch (error) {
      datos = {};
    }
    const mensaje =
      datos.error || "El servidor respondió " + respuesta.status + ".";
    const reintentable = !(respuesta.status >= 400 && respuesta.status < 500);
    return { ok: false, reintentable: reintentable, mensaje: mensaje };
  }

  /** Programa el reintento del primer ítem que aún no puede enviarse. */
  function programarReintento(momento) {
    if (temporizador) clearTimeout(temporizador);
    const demora = Math.max(1000, momento - Date.now());
    temporizador = setTimeout(() => {
      temporizador = null;
      sincronizar();
    }, demora);
  }

  /** Borra los ítems enviados más antiguos cuando la cola crece. */
  async function podarEnviados(items) {
    const enviados = items.filter((item) => item.estado === "enviado");
    if (enviados.length <= MAXIMO_ENVIADOS_GUARDADOS) return;
    const sobrantes = enviados.slice(0, enviados.length - MAXIMO_ENVIADOS_GUARDADOS);
    for (const item of sobrantes) {
      await global.SAOutbox.eliminar(item.client_request_id);
    }
  }

  /** Drena la cola en orden FIFO. */
  async function sincronizar() {
    if (sincronizando) return { enviados: 0, errores: 0 };
    if (!global.SAOutbox || !global.SAOutbox.disponible()) {
      return { enviados: 0, errores: 0 };
    }
    sincronizando = true;
    let enviados = 0;
    let errores = 0;
    try {
      const items = await global.SAOutbox.listar();
      const yo = await usuarioActual();
      for (const item of items) {
        if (item.estado !== "pendiente") continue;
        if (!yo) break; // sin sesión no se puede enviar: se reintenta luego

        if (item.autor_id && yo.id !== item.autor_id) {
          await global.SAOutbox.actualizar(item.client_request_id, {
            estado: "error",
            last_error:
              "Este reporte pertenece a otra cuenta: inicia sesión con la cuenta original.",
          });
          errores += 1;
          notificar({ tipo: "error", item: item });
          continue;
        }

        const esperaHasta = item.next_attempt_at || 0;
        if (Date.now() < esperaHasta) {
          programarReintento(esperaHasta);
          break;
        }

        const resultado = await enviar(item);
        if (resultado.ok) {
          await global.SAOutbox.actualizar(item.client_request_id, {
            estado: "enviado",
            combat_id: resultado.combate ? resultado.combate.id : null,
            last_error: "",
            next_attempt_at: 0,
            intentos: item.intentos + 1,
          });
          enviados += 1;
          notificar({ tipo: "enviado", item: item, combate: resultado.combate });
          continue;
        }

        if (!resultado.reintentable) {
          await global.SAOutbox.actualizar(item.client_request_id, {
            estado: "error",
            last_error: resultado.mensaje,
            intentos: item.intentos + 1,
          });
          errores += 1;
          notificar({ tipo: "error", item: item });
          continue;
        }

        const intentos = item.intentos + 1;
        const proximo = Date.now() + esperaPara(intentos);
        await global.SAOutbox.actualizar(item.client_request_id, {
          estado: "pendiente",
          last_error: resultado.mensaje,
          intentos: intentos,
          next_attempt_at: proximo,
        });
        programarReintento(proximo);
        break; // se conserva el orden FIFO de la cola
      }
      await podarEnviados(await global.SAOutbox.listar());
    } finally {
      sincronizando = false;
    }
    notificar({ tipo: "fin", enviados: enviados, errores: errores });
    return { enviados: enviados, errores: errores };
  }

  /** Encola un reporte y notifica a la UI. */
  async function encolar(payload, meta) {
    const clave = meta && meta.client_request_id ? meta.client_request_id : nuevaClave();
    const item = await global.SAOutbox.encolar(payload, Object.assign({}, meta, {
      client_request_id: clave,
    }));
    notificar({ tipo: "encolado", item: item });
    return item;
  }

  if (typeof global.addEventListener === "function") {
    global.addEventListener("online", () => {
      sincronizar();
    });
  }

  global.SASync = {
    sincronizar: sincronizar,
    encolar: encolar,
    nuevaClave: nuevaClave,
    esperaPara: esperaPara,
    ESPERA_INICIAL_MS: ESPERA_INICIAL_MS,
    ESPERA_MAXIMA_MS: ESPERA_MAXIMA_MS,
  };

  // Al abrir la app se intenta vaciar la cola (si hay red y sesión).
  if (global.document && global.addEventListener) {
    global.addEventListener("load", () => {
      sincronizar();
    });
  }
})(typeof window !== "undefined" ? window : this);
