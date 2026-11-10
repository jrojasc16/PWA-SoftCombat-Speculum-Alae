/* Panel de administración (Sprint 10): gestión de usuarios.
 *
 * Las acciones hablan con la **misma API JSON** que usa el resto de la PWA
 * (mismo origen, cookie de sesión):
 *   - PATCH /admin/users/<id> → activar/desactivar y cambiar el rol
 *
 * El service worker nunca cachea /admin: estas páginas siempre van a la red.
 */
(function () {
  "use strict";

  const estadoUsuarios = document.getElementById("estado-usuarios");
  const tablaUsuarios = document.querySelector("table.tabla");

  if (!estadoUsuarios) return;

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
})();
