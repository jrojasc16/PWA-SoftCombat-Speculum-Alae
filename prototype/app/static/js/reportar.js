/* Página /reportar (Sprint 7.6, Sprint 9.2): envía el reporte a POST /combats.
 *
 * El formulario usa el mismo contrato JSON que la API: los datalists se
 * llenan con el directorio de la comunidad (GET /me/community), el nombre se
 * resuelve a id en el cliente y el envío es un fetch con JSON. El combate
 * queda PENDIENTE hasta que el rival (o el árbitro) lo confirme (RF6).
 *
 * Si no hay red, el reporte **no se pierde**: se encola en la base de datos
 * local (``outbox`` de ``db.js``) con su clave de idempotencia y se envía
 * solo al recuperar la conexión (``js/sync.js``).
 */
(function () {
  "use strict";

  const formulario = document.getElementById("form-reporte");
  if (!formulario) return;

  const estado = document.getElementById("estado-reporte");
  const campoOponente = document.getElementById("oponente");
  const campoArbitro = document.getElementById("arbitro");
  const campoResultado = document.getElementById("resultado");
  const campoJugado = document.getElementById("jugado");
  const listaJugadores = document.getElementById("lista-jugadores");
  const listaArbitros = document.getElementById("lista-arbitros");

  let jugadores = [];
  let arbitros = [];
  let yo = null;

  function mostrar(texto, esError) {
    estado.textContent = texto;
    estado.className = "mensaje " + (esError ? "mensaje-error" : "mensaje-ok");
    estado.hidden = false;
  }

  function llenarDatalist(lista, personas) {
    lista.textContent = "";
    for (const persona of personas) {
      const opcion = document.createElement("option");
      opcion.value = persona.name;
      lista.appendChild(opcion);
    }
  }

  function resolverId(personas, nombre) {
    const texto = nombre.trim().toLowerCase();
    const enlaces = personas.filter((p) => p.name.trim().toLowerCase() === texto);
    return enlaces.length === 1 ? enlaces[0].id : null;
  }

  /** Guarda el directorio en la base local para poder usarlo sin conexión. */
  function guardarDirectorioLocal(datos) {
    if (!window.SAOutbox || !window.SAOutbox.disponible()) return;
    window.SAOutbox.guardarDirectorio(datos).catch(() => null);
  }

  /** Carga el directorio de la comunidad (con red o desde la copia local). */
  async function cargarDirectorio() {
    try {
      const respuesta = await fetch("/me/community", {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!respuesta.ok) throw new Error("directorio no disponible");
      const datos = await respuesta.json();
      yo = datos.yo;
      jugadores = datos.jugadores;
      arbitros = datos.arbitros;
      llenarDatalist(listaJugadores, jugadores);
      llenarDatalist(listaArbitros, arbitros);
      guardarDirectorioLocal(datos);
      return;
    } catch (error) {
      // Sin red: se intenta con la copia guardada en el dispositivo.
      let local = null;
      if (window.SAOutbox && window.SAOutbox.disponible()) {
        local = await window.SAOutbox.leerDirectorio().catch(() => null);
      }
      if (local) {
        yo = local.yo;
        jugadores = local.jugadores || [];
        arbitros = local.arbitros || [];
        llenarDatalist(listaJugadores, jugadores);
        llenarDatalist(listaArbitros, arbitros);
        mostrar(
          "Sin conexión: se muestra el directorio guardado en este dispositivo.",
          false
        );
        return;
      }
      mostrar("No se pudo cargar el directorio de la comunidad.", true);
    }
  }

  /** Encola el reporte para enviarlo cuando vuelva la red. */
  async function encolarReporte(cuerpo, resumen, clave) {
    if (!window.SASync || !window.SAOutbox || !window.SAOutbox.disponible()) {
      mostrar(
        "Sin conexión y este navegador no permite guardar el reporte: inténtalo de nuevo cuando vuelva la red.",
        true
      );
      return false;
    }
    try {
      await window.SASync.encolar(cuerpo, {
        autor_id: yo ? yo.id : null,
        resumen: resumen,
        client_request_id: clave,
      });
      mostrar(
        "Sin conexión: el reporte quedó guardado y se enviará solo al recuperar la red.",
        false
      );
      formulario.reset();
      return true;
    } catch (error) {
      mostrar("No se pudo guardar el reporte para enviarlo más tarde.", true);
      return false;
    }
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    if (!yo) {
      mostrar("El directorio aún no está cargado. Inténtalo de nuevo.", true);
      return;
    }
    const idOponente = resolverId(jugadores, campoOponente.value);
    if (idOponente === null) {
      mostrar("Elige un oponente existente de la lista.", true);
      return;
    }
    let idArbitro = null;
    if (campoArbitro.value.trim() !== "") {
      idArbitro = resolverId(arbitros, campoArbitro.value);
      if (idArbitro === null) {
        mostrar("Elige un árbitro existente de la lista (o deja vacío).", true);
        return;
      }
    }

    const idGanador = campoResultado.value === "yo" ? yo.id : idOponente;
    const cuerpo = {
      participants: [yo.id, idOponente],
      winner: idGanador,
      played_at: campoJugado.value, // datetime-local: ISO-8601 sin huso
    };
    if (idArbitro !== null) cuerpo.referee_id = idArbitro;

    const resumen = {
      oponente: campoOponente.value.trim(),
      resultado: campoResultado.value === "yo" ? "Gané yo" : "Ganó el oponente",
      jugado: cuerpo.played_at,
    };

    // La clave de idempotencia se genera **antes** de enviar: si la respuesta
    // se pierde por un corte de red, el reintento usa la misma clave y el
    // servidor no crea un combate duplicado (Sprint 4.5).
    const clave = window.SASync ? window.SASync.nuevaClave() : null;

    // Sin red no se intenta ni el envío: se encola directamente.
    if (!navigator.onLine) {
      await encolarReporte(cuerpo, resumen, clave);
      return;
    }

    // Se bloquea el botón mientras se envía: dos envíos con la misma sesión
    // generarían dos claves y, por tanto, dos combates.
    const boton = formulario.querySelector('button[type="submit"]');
    if (boton) boton.disabled = true;

    try {
      const respuesta = await fetch("/combats", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(
          Object.assign({}, cuerpo, { client_request_id: clave })
        ),
      });
      const datos = await respuesta.json();
      if (respuesta.ok) {
        // 200 = el servidor ya tenía ese reporte (reenvío): no es un error.
        mostrar(
          respuesta.status === 200
            ? "Ese combate ya estaba registrado (#" + datos.id + ")."
            : "Combate #" + datos.id + " registrado. Queda pendiente de confirmación.",
          false
        );
        formulario.reset();
      } else {
        mostrar(datos.error || "No se pudo registrar el combate.", true);
      }
    } catch (_error) {
      // La red se cayó durante el envío: el reporte no se pierde.
      await encolarReporte(cuerpo, resumen, clave);
    } finally {
      if (boton) boton.disabled = false;
    }
  });

  cargarDirectorio();
})();
