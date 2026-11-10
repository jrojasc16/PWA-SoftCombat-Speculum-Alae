/* Espera el resultado de una página usando el protocolo DevTools (CDP).
 *
 * Herramienta auxiliar de `scripts/verificar_offline_browser.py`: abre una URL
 * en el navegador que ya está escuchando en un puerto de depuración y espera a
 * que un elemento de la página deje de estar en su estado inicial ("PENDIENTE").
 *
 * Uso:
 *   node cdp_esperar_resultado.mjs --port 9333 --url http://... --selector "#resultado"
 *
 * Imprime por stdout un JSON: {"valor": "<texto del elemento>"} y termina con
 * código 0 si se obtuvo el valor, 1 si no.
 */

const args = process.argv.slice(2);

function opcion(nombre, porDefecto) {
  const indice = args.indexOf("--" + nombre);
  return indice >= 0 && indice + 1 < args.length ? args[indice + 1] : porDefecto;
}

const puerto = opcion("port", "9333");
const url = opcion("url");
const selector = opcion("selector", "#resultado");
const timeoutMs = Number(opcion("timeout-ms", "90000"));

if (!url) {
  console.error("Falta --url");
  process.exit(1);
}

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

async function esperarObjetivo() {
  const limite = Date.now() + 30000;
  while (Date.now() < limite) {
    try {
      const respuesta = await fetch(`http://127.0.0.1:${puerto}/json/list`);
      const lista = await respuesta.json();
      const pagina = lista.find((objetivo) => objetivo.type === "page");
      if (pagina) return pagina;
    } catch (error) {
      /* el navegador aún no escucha */
    }
    await dormir(300);
  }
  throw new Error("No se encontró ninguna pestaña en el navegador.");
}

function conectar(direccion) {
  return new Promise((resolver, rechazar) => {
    const socket = new WebSocket(direccion);
    socket.addEventListener("open", () => resolver(socket));
    socket.addEventListener("error", () =>
      rechazar(new Error("No se pudo conectar con el navegador."))
    );
  });
}

let siguienteId = 1;

function enviar(socket, metodo, parametros) {
  const id = siguienteId++;
  return new Promise((resolver, rechazar) => {
    const manejador = (evento) => {
      const datos = JSON.parse(evento.data);
      if (datos.id !== id) return;
      socket.removeEventListener("message", manejador);
      if (datos.error) rechazar(new Error(JSON.stringify(datos.error)));
      else resolver(datos.result);
    };
    socket.addEventListener("message", manejador);
    socket.send(JSON.stringify({ id, method: metodo, params: parametros }));
  });
}

async function principal() {
  const objetivo = await esperarObjetivo();
  const socket = await conectar(objetivo.webSocketDebuggerUrl);
  try {
    await enviar(socket, "Page.enable", {});
    await enviar(socket, "Page.navigate", { url });
    await dormir(500);
    const expresion = `(async () => {
      const limite = Date.now() + ${timeoutMs};
      while (Date.now() < limite) {
        const nodo = document.querySelector(${JSON.stringify(selector)});
        const texto = nodo ? (nodo.textContent || "") : "";
        if (texto && texto !== "PENDIENTE") return texto;
        await new Promise((r) => setTimeout(r, 250));
      }
      return "TIMEOUT";
    })()`;
    const resultado = await enviar(socket, "Runtime.evaluate", {
      expression: expresion,
      awaitPromise: true,
      returnByValue: true,
    });
    const valor = resultado && resultado.result ? resultado.result.value : "";
    console.log(JSON.stringify({ valor }));
    process.exit(valor && valor !== "TIMEOUT" ? 0 : 1);
  } finally {
    try {
      socket.close();
    } catch (error) {
      /* nada que hacer */
    }
  }
}

principal().catch((error) => {
  console.error(String(error.message || error));
  process.exit(1);
});
