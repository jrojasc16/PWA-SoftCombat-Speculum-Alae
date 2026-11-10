/* Base de datos local del navegador (Sprint 9.1): cola de salida (outbox).
 *
 * Envuelve IndexedDB con una API mínima y sin dependencias externas:
 *
 * - Store ``outbox``: cola FIFO de reportes de combate pendientes de envío.
 *   Cada ítem guarda el payload, la clave de idempotencia
 *   (``client_request_id``), el autor, los intentos y el estado
 *   (``pendiente`` / ``enviado`` / ``error``). El orden de la cola es el orden
 *   de inserción (clave ``id`` autoincremental).
 * - Store ``directorio``: copia local del directorio de la comunidad
 *   (``GET /me/community``) para poder reportar **sin conexión** (sin red no
 *   hay forma de resolver el nombre del oponente).
 *
 * Si el navegador no soporta IndexedDB, las funciones rechazan con un error
 * legible y la UI informa de que el envío offline no está disponible.
 */
(function (global) {
  "use strict";

  const NOMBRE_BD = "speculum-alae";
  const VERSION_BD = 1;
  const STORE_OUTBOX = "outbox";
  const STORE_DIRECTORIO = "directorio";
  const CLAVE_DIRECTORIO = "comunidad-actual";

  const ESTADO_PENDIENTE = "pendiente";
  const ESTADO_ENVIADO = "enviado";
  const ESTADO_ERROR = "error";

  /** Error de negocio de la cola local (mensaje apto para la UI). */
  function ErrorOutbox(mensaje) {
    this.name = "ErrorOutbox";
    this.message = mensaje;
  }
  ErrorOutbox.prototype = Object.create(Error.prototype);

  /** ¿El navegador soporta IndexedDB? */
  function disponible() {
    return typeof global.indexedDB !== "undefined" && global.indexedDB !== null;
  }

  /** Abre (y crea si hace falta) la base de datos local. */
  function abrir() {
    if (!disponible()) {
      return Promise.reject(
        new ErrorOutbox("Este navegador no soporta IndexedDB: no hay envío offline.")
      );
    }
    return new Promise((resolver, rechazar) => {
      const peticion = global.indexedDB.open(NOMBRE_BD, VERSION_BD);
      peticion.onupgradeneeded = (evento) => {
        const bd = evento.target.result;
        if (!bd.objectStoreNames.contains(STORE_OUTBOX)) {
          const store = bd.createObjectStore(STORE_OUTBOX, {
            keyPath: "id",
            autoIncrement: true,
          });
          store.createIndex("client_request_id", "client_request_id", {
            unique: true,
          });
          store.createIndex("estado", "estado", { unique: false });
        }
        if (!bd.objectStoreNames.contains(STORE_DIRECTORIO)) {
          bd.createObjectStore(STORE_DIRECTORIO, { keyPath: "clave" });
        }
      };
      peticion.onsuccess = () => resolver(peticion.result);
      peticion.onerror = () =>
        rechazar(new ErrorOutbox("No se pudo abrir la base de datos local."));
    });
  }

  /** Ejecuta una operación sobre un store y devuelve su resultado. */
  function conAlmacen(nombre, modo, operacion) {
    return abrir().then(
      (bd) =>
        new Promise((resolver, rechazar) => {
          const transaccion = bd.transaction(nombre, modo);
          const store = transaccion.objectStore(nombre);
          let peticion = null;
          try {
            peticion = operacion(store);
          } catch (error) {
            bd.close();
            rechazar(error);
            return;
          }
          const esPeticion =
            peticion && typeof peticion === "object" && "onsuccess" in peticion;
          transaccion.oncomplete = () => {
            bd.close();
            resolver(esPeticion ? peticion.result : peticion);
          };
          transaccion.onerror = () => {
            bd.close();
            rechazar(new ErrorOutbox("Error en la base de datos local."));
          };
          transaccion.onabort = () => {
            bd.close();
            rechazar(new ErrorOutbox("La operación local se abortó."));
          };
        })
    );
  }

  const Outbox = {
    ESTADO_PENDIENTE: ESTADO_PENDIENTE,
    ESTADO_ENVIADO: ESTADO_ENVIADO,
    ESTADO_ERROR: ESTADO_ERROR,
    STORE_OUTBOX: STORE_OUTBOX,
    STORE_DIRECTORIO: STORE_DIRECTORIO,

    disponible: disponible,

    /**
     * Encola un reporte y devuelve el ítem creado.
     *
     * @param {object} payload cuerpo que se enviará a ``POST /combats``.
     * @param {object} meta datos de control (clave de idempotencia, autor y
     *                     resumen para la lista de pendientes).
     */
    encolar(payload, meta) {
      const ahora = new Date().toISOString();
      const item = {
        client_request_id: meta.client_request_id,
        payload: payload,
        autor_id: meta.autor_id || null,
        autor_email: meta.autor_email || "",
        resumen: meta.resumen || {},
        estado: ESTADO_PENDIENTE,
        intentos: 0,
        combat_id: null,
        last_error: "",
        next_attempt_at: 0,
        created_at: ahora,
        updated_at: ahora,
      };
      return conAlmacen(STORE_OUTBOX, "readwrite", (store) =>
        store.add(item)
      ).then(() => Outbox.listarPorClave(item.client_request_id));
    },

    /** Lista la cola en orden FIFO (por clave autoincremental). */
    listar() {
      return conAlmacen(STORE_OUTBOX, "readonly", (store) =>
        store.getAll()
      ).then((items) =>
        (items || []).sort((a, b) => (a.id || 0) - (b.id || 0))
      );
    },

    /** Devuelve el ítem con esa clave de idempotencia (o ``null``). */
    listarPorClave(clientRequestId) {
      return conAlmacen(STORE_OUTBOX, "readonly", (store) =>
        store.index("client_request_id").get(clientRequestId)
      ).then((item) => item || null);
    },

    /** Actualiza campos de un ítem (estado, intentos, errores…). */
    actualizar(clientRequestId, cambios) {
      return Outbox.listarPorClave(clientRequestId).then((item) => {
        if (!item) return null;
        const actualizado = Object.assign({}, item, cambios, {
          updated_at: new Date().toISOString(),
        });
        return conAlmacen(STORE_OUTBOX, "readwrite", (store) =>
          store.put(actualizado)
        ).then(() => actualizado);
      });
    },

    /** Elimina un ítem de la cola. */
    eliminar(clientRequestId) {
      return Outbox.listarPorClave(clientRequestId).then((item) => {
        if (!item) return false;
        return conAlmacen(STORE_OUTBOX, "readwrite", (store) =>
          store.delete(item.id)
        ).then(() => true);
      });
    },

    /** Vacía la cola completa. */
    vaciar() {
      return conAlmacen(STORE_OUTBOX, "readwrite", (store) => store.clear());
    },

    /** Número de ítems que aún no se han enviado. */
    contarPendientes() {
      return Outbox.listar().then(
        (items) =>
          (items || []).filter((item) => item.estado === ESTADO_PENDIENTE).length
      );
    },

    /** Guarda la copia local del directorio de la comunidad. */
    guardarDirectorio(datos) {
      return conAlmacen(STORE_DIRECTORIO, "readwrite", (store) =>
        store.put({ clave: CLAVE_DIRECTORIO, datos: datos, updated_at: new Date().toISOString() })
      );
    },

    /** Lee la copia local del directorio de la comunidad (o ``null``). */
    leerDirectorio() {
      return conAlmacen(STORE_DIRECTORIO, "readonly", (store) =>
        store.get(CLAVE_DIRECTORIO)
      ).then((fila) => (fila && fila.datos) || null);
    },

    /** Borra la copia local del directorio (al cerrar sesión). */
    borrarDirectorio() {
      return conAlmacen(STORE_DIRECTORIO, "readwrite", (store) =>
        store.delete(CLAVE_DIRECTORIO)
      );
    },
  };

  global.SAOutbox = Outbox;
})(typeof window !== "undefined" ? window : this);
