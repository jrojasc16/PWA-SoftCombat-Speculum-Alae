/* JS de la página sin conexión (Sprint 8.3).
 *
 * Pide al service worker las copias guardadas del ranking público y del
 * historial propio y las pinta en dos tablas simples. Solo usa datos ya
 * cacheados en el dispositivo: nunca intenta ir al servidor.
 */
(function () {
  "use strict";

  function pedirDatosCacheados() {
    return new Promise((resolver) => {
      if (!navigator.serviceWorker || !navigator.serviceWorker.controller) {
        resolver({});
        return;
      }
      const canal = new MessageChannel();
      const limite = setTimeout(() => resolver({}), 3000);
      canal.port1.onmessage = (evento) => {
        clearTimeout(limite);
        resolver((evento.data && evento.data.datos) || {});
      };
      navigator.serviceWorker.controller.postMessage(
        { tipo: "sa-datos-cache" },
        [canal.port2]
      );
    });
  }

  function tabla(columnas, filas) {
    if (!filas || filas.length === 0) {
      return '<p class="vacio">No hay copia guardada de esta lectura.</p>';
    }
    const cabecera = columnas
      .map((columna) => "<th scope=\"col\">" + columna.titulo + "</th>")
      .join("");
    const cuerpo = filas
      .map((fila) => {
        const celdas = columnas
          .map((columna) => "<td>" + columna.valor(fila) + "</td>")
          .join("");
        return "<tr>" + celdas + "</tr>";
      })
      .join("");
    return (
      '<table class="tabla"><thead><tr>' +
      cabecera +
      "</tr></thead><tbody>" +
      cuerpo +
      "</tbody></table>"
    );
  }

  function escapar(texto) {
    const div = document.createElement("div");
    div.textContent = texto === null || texto === undefined ? "" : String(texto);
    return div.innerHTML;
  }

  function pintarRanking(datos) {
    const destino = document.getElementById("ranking-offline");
    if (!destino) return;
    const items = (datos && datos.items) || [];
    destino.innerHTML = tabla(
      [
        { titulo: "Pos.", valor: (fila) => escapar(fila.position) },
        { titulo: "Jugador", valor: (fila) => escapar(fila.name) },
        {
          titulo: "Puntos",
          valor: (fila) => escapar(Number(fila.points).toFixed(1)),
        },
        {
          titulo: "Combates",
          valor: (fila) => escapar(fila.matches_played),
        },
      ],
      items
    );
  }

  function pintarHistorial(datos) {
    const destino = document.getElementById("historial-offline");
    if (!destino) return;
    const items = (datos && datos.items) || [];
    destino.innerHTML = tabla(
      [
        {
          titulo: "Fecha",
          valor: (fila) => escapar((fila.played_at || "").slice(0, 16).replace("T", " ")),
        },
        {
          titulo: "Rival",
          valor: (fila) =>
            escapar(fila.opponent ? fila.opponent.name : "—"),
        },
        { titulo: "Resultado", valor: (fila) => escapar(fila.result || "—") },
        { titulo: "Estado", valor: (fila) => escapar(fila.status) },
        {
          titulo: "Índice",
          valor: (fila) =>
            fila.rating
              ? escapar(
                  Number(fila.rating.points_before).toFixed(1) +
                    " → " +
                    Number(fila.rating.points_after).toFixed(1) +
                    " (" +
                    (fila.rating.delta >= 0 ? "+" : "") +
                    Number(fila.rating.delta).toFixed(1) +
                    ")"
                )
              : "sin procesar",
        },
      ],
      items
    );
  }

  pedirDatosCacheados().then((datos) => {
    pintarRanking(datos["/api/ranking"]);
    pintarHistorial(datos["/me/history"]);
  });
})();
