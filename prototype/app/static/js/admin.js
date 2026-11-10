/* Panel de administración (Sprint 10): gestión de usuarios y resolución de
 * conflictos.
 *
 * Las acciones hablan con la **misma API JSON** que usa el resto de la PWA
 * (mismo origen, cookie de sesión):
 *   - PATCH /admin/users/<id>   → activar/desactivar y cambiar el rol
 *   - PATCH /admin/combats/<id> → editar el resultado (queda auditado)
 *
 * El service worker nunca cachea /admin: estas páginas siempre van a la red.
 */
(function () {
  "use strict";

  const estadoUsuarios = document.getElementById("estado-usuarios");
  const estadoCombates = document.getElementById("estado-combates");
  const tablaUsuarios = document.querySelector("table.tabla");
  const listaCombates = document.getElementById("lista-combates");

  if (!estadoUsuarios && !estadoCombates) return;

  function mostrar(elemento, texto, esError) {
    if (!elemento) return;
    elemento.textContent = texto;
    elemento.className = "mensaje " + (esError ? "mensaje-error" : "mensaje-ok");
    elemento.hidden = false;
  }

  /** Envía una acción a la API admin y devuelve el cuerpo de la respuesta. */
  async function enviar(url, metodo, cuerpo) {
    const respuesta = await fetch(url, {
      method: metodo,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      credentials: "same-origin",
      body: JSON.stringify(cuerpo),
    });
    let datos = null;
    try {
      datos = await respuesta.json();
    } catch (error) {
      datos = null;
    }
    if (!respuesta.ok) {
      const mensaje =
        (datos && datos.error) || "No se pudo completar la operación.";
      throw new Error(mensaje);
    }
    return datos;
  }

  // --- Usuarios: activar/desactivar y cambiar rol (UC10/UC11) ----------------

  function alPulsarEstado(evento) {
    const boton = evento.target.closest(".btn-estado");
    if (!boton) return;
    const id = boton.dataset.id;
    const activo = boton.dataset.activo !== "1";
    boton.disabled = true;
    enviar("/admin/users/" + id, "PATCH", { active: activo })
      .then((usuario) => {
        mostrar(
          estadoUsuarios,
          usuario.name + ": cuenta " + (usuario.active ? "activada" : "desactivada"),
          false
        );
        window.location.reload();
      })
      .catch((error) => {
        mostrar(estadoUsuarios, error.message, true);
        boton.disabled = false;
      });
  }

  function alPulsarRol(evento) {
    const boton = evento.target.closest(".btn-rol");
    if (!boton) return;
    const fila = boton.closest("tr");
    const selector = fila.querySelector(".selector-rol");
    const id = boton.dataset.id;
    boton.disabled = true;
    enviar("/admin/users/" + id, "PATCH", { role: selector.value })
      .then((usuario) => {
        mostrar(
          estadoUsuarios,
          usuario.name + ": rol cambiado a " + usuario.role,
          false
        );
      })
      .catch((error) => {
        mostrar(estadoUsuarios, error.message, true);
      })
      .finally(() => {
        boton.disabled = false;
      });
  }

  if (tablaUsuarios) {
    tablaUsuarios.addEventListener("click", alPulsarEstado);
    tablaUsuarios.addEventListener("click", alPulsarRol);
  }

  // --- Combates: editar el resultado de un conflicto (UC12) -----------------

  if (listaCombates) {
    listaCombates.addEventListener("submit", (evento) => {
      const formulario = evento.target.closest(".form-editar");
      if (!formulario) return;
      evento.preventDefault();

      const id = formulario.dataset.id;
      const ganador = formulario.querySelector('[name="winner_id"]').value;
      const fecha = formulario.querySelector('[name="played_at"]').value;
      if (!ganador) {
        mostrar(estadoCombates, "Elige al ganador real del combate.", true);
        return;
      }

      const boton = formulario.querySelector('button[type="submit"]');
      boton.disabled = true;
      const cuerpo = { winner_id: Number(ganador) };
      if (fecha) cuerpo.played_at = fecha;

      enviar("/admin/combats/" + id, "PATCH", cuerpo)
        .then((combate) => {
          mostrar(
            estadoCombates,
            "Combate #" + combate.id + " guardado y resuelto (" + combate.status + ").",
            false
          );
          window.location.reload();
        })
        .catch((error) => {
          mostrar(estadoCombates, error.message, true);
          boton.disabled = false;
        });
    });
  }
})();
