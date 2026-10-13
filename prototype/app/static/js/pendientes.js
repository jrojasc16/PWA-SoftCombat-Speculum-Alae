/* Página /pendientes (Sprint 7.6): lista GET /combats/pending y confirma.
 *
 * Cada tarjeta muestra los dos participantes con sus nombres (sin correos) y
 * un desplegable para elegir el ganador; al confirmar se envía
 * POST /combats/<id>/confirm con {"winner_id": …} (mismo contrato que la
 * API, RF8) y la lista se recarga.
 */
(function () {
  "use strict";

  const lista = document.getElementById("lista-pendientes");
  if (!lista) return;

  const estado = document.getElementById("estado-pendientes");
  const MESES_ES = [
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
  ];

  function mostrar(texto, esError) {
    estado.textContent = texto;
    estado.className = "mensaje " + (esError ? "mensaje-error" : "mensaje-ok");
    estado.hidden = false;
  }

  function fechaLegible(iso) {
    // played_at es ISO-8601 naive en UTC (SQLite no guarda husos).
    const fecha = new Date(iso.endsWith("Z") ? iso : iso + "Z");
    if (Number.isNaN(fecha.getTime())) return iso;
    const dia = fecha.getDate();
    const mes = MESES_ES[fecha.getMonth()];
    const horas = String(fecha.getHours()).padStart(2, "0");
    const minutos = String(fecha.getMinutes()).padStart(2, "0");
    return `${dia} ${mes} ${fecha.getFullYear()}, ${horas}:${minutos}`;
  }

  function tarjetaCombate(combate) {
    const tarjeta = document.createElement("div");
    tarjeta.className = "tarjeta";

    const titulo = document.createElement("p");
    titulo.textContent =
      "Combate #" + combate.id + " — " + fechaLegible(combate.played_at);
    tarjeta.appendChild(titulo);

    const formulario = document.createElement("form");
    const rival = document.createElement("p");
    rival.textContent =
      "Participantes: " +
      combate.participants.map((p) => p.name).join(" vs. ");
    formulario.appendChild(rival);

    const etiqueta = document.createElement("label");
    etiqueta.textContent = "¿Quién ganó?";
    formulario.appendChild(etiqueta);

    const selector = document.createElement("select");
    selector.required = true;
    for (const participante of combate.participants) {
      const opcion = document.createElement("option");
      opcion.value = String(participante.user_id);
      opcion.textContent = participante.name;
      selector.appendChild(opcion);
    }
    formulario.appendChild(selector);

    const boton = document.createElement("button");
    boton.type = "submit";
    boton.className = "boton";
    boton.textContent = "Confirmar";
    formulario.appendChild(boton);

    formulario.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      boton.disabled = true;
      try {
        const respuesta = await fetch("/combats/" + combate.id + "/confirm", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ winner_id: Number(selector.value) }),
        });
        const datos = await respuesta.json();
        if (respuesta.ok) {
          mostrar(
            "Combate #" + combate.id + ": tu confirmación quedó registrada (" +
              datos.status + ").",
            false
          );
          tarjeta.remove();
          if (!lista.querySelector(".tarjeta")) {
            lista.innerHTML =
              '<p class="vacio">No tienes combates pendientes de confirmación.</p>';
          }
        } else {
          mostrar(datos.error || "No se pudo confirmar el combate.", true);
          boton.disabled = false;
        }
      } catch (_error) {
        mostrar("Sin conexión: inténtalo de nuevo cuando vuelva la red.", true);
        boton.disabled = false;
      }
    });

    tarjeta.appendChild(formulario);
    return tarjeta;
  }

  async function cargarPendientes() {
    try {
      const respuesta = await fetch("/combats/pending", {
        headers: { Accept: "application/json" },
      });
      if (!respuesta.ok) {
        mostrar("No se pudieron cargar tus combates pendientes.", true);
        return;
      }
      const combates = await respuesta.json();
      lista.textContent = "";
      if (combates.length === 0) {
        lista.innerHTML =
          '<p class="vacio">No tienes combates pendientes de confirmación.</p>';
        return;
      }
      for (const combate of combates) {
        lista.appendChild(tarjetaCombate(combate));
      }
    } catch (_error) {
      mostrar("Sin conexión: inténtalo de nuevo cuando vuelva la red.", true);
    }
  }

  cargarPendientes();
})();
