/* Página /reportar (Sprint 7.6): envía el reporte a POST /combats.
 *
 * El formulario usa el mismo contrato JSON que la API: los datalists se
 * llenan con el directorio de la comunidad (GET /me/community), el nombre se
 * resuelve a id en el cliente y el envío es un fetch con JSON. El combate
 * queda PENDIENTE hasta que el rival (o el árbitro) lo confirme (RF6).
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

  async function cargarDirectorio() {
    const respuesta = await fetch("/me/community", {
      headers: { Accept: "application/json" },
    });
    if (!respuesta.ok) {
      mostrar("No se pudo cargar el directorio de la comunidad.", true);
      return;
    }
    const datos = await respuesta.json();
    yo = datos.yo;
    jugadores = datos.jugadores;
    arbitros = datos.arbitros;
    llenarDatalist(listaJugadores, jugadores);
    llenarDatalist(listaArbitros, arbitros);
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

    try {
      const respuesta = await fetch("/combats", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(cuerpo),
      });
      const datos = await respuesta.json();
      if (respuesta.ok) {
        mostrar(
          "Combate #" + datos.id + " registrado. Queda pendiente de confirmación.",
          false
        );
        formulario.reset();
      } else {
        mostrar(datos.error || "No se pudo registrar el combate.", true);
      }
    } catch (_error) {
      mostrar("Sin conexión: inténtalo de nuevo cuando vuelva la red.", true);
    }
  });

  cargarDirectorio();
})();
