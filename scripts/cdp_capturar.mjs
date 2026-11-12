/* Captura pantallazos con el protocolo DevTools (CDP) para el manual de usuario.
 *
 * Herramienta auxiliar de `scripts/capturar_manual_usuario.py`: recorre una
 * lista de pasos (navegar → ejecutar JS opcional → esperar un selector →
 * guardar un PNG) en el navegador que ya está escuchando en un puerto de
 * depuración.
 *
 * Uso:
 *   node cdp_capturar.mjs --port 9333 --plan ruta/al/plan.json --salida E:\...\capturas
 *
 * El plan es un archivo JSON con una lista de pasos:
 *   [{"nombre": "...", "url": "...", "js": "...", "esperar": "#selector",
 *     "sin_texto": "Cargando", "captura": "01-x.png"}, ...]
 *   - `js` (opcional): expresión asíncrona que se evalúa tras navegar;
 *     si resuelve `false` el paso se considera fallido.
 *   - `esperar` / `sin_texto` (opcional): el paso espera a que exista el
 *     selector y (si se indica) su texto no contenga `sin_texto`.
 *   - `captura` (opcional): nombre del PNG a guardar en `--salida`.
 *
 * El progreso va a stderr y el resultado final a stdout:
 *   {"capturas": ["01-x.png", ...]} con código 0, o
 *   {"error": "...", "paso": "..."} con código 1.
 */

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);

function opcion(nombre, porDefecto) {
  const indice = args.indexOf("--" + nombre);
  return indice >= 0 && indice + 1 < args.length ? args[indice + 1] : porDefecto;
}

const puerto = opcion("port", "9333");
const planRuta = opcion("plan");
const salida = opcion("salida");
const timeoutMs = Number(opcion("timeout-ms", "25000"));

if (!planRuta || !salida) {
  console.error("Faltan --plan o --salida");
  process.exit(1);
}
if (!existsSync(planRuta)) {
  console.error(`No existe el plan: ${planRuta}`);
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

async function evaluar(socket, expresion) {
  const resultado = await enviar(socket, "Runtime.evaluate", {
    expression: expresion,
    awaitPromise: true,
    returnByValue: true,
  });
  return resultado && resultado.result ? resultado.result.value : undefined;
}

async function esperarSelector(socket, selector, sinTexto, limiteMs) {
  const fin = Date.now() + limiteMs;
  while (Date.now() < fin) {
    const listo = await evaluar(
      socket,
      `(async () => {
        const nodo = document.querySelector(${JSON.stringify(selector)});
        if (!nodo) return false;
        const texto = nodo.textContent || "";
        return ${sinTexto ? `!texto.includes(${JSON.stringify(sinTexto)})` : "true"};
      })()`
    );
    if (listo) return true;
    await dormir(200);
  }
  return false;
}

async function principal() {
  const plan = JSON.parse(readFileSync(planRuta, "utf8"));
  const objetivo = await esperarObjetivo();
  const socket = await conectar(objetivo.webSocketDebuggerUrl);
  try {
    await enviar(socket, "Page.enable", {});
    await enviar(socket, "Emulation.setDeviceMetricsOverride", {
      width: 1280,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const capturas = [];
    for (const paso of plan) {
      const navegacion = await enviar(socket, "Page.navigate", { url: paso.url });
      if (
        navegacion &&
        navegacion.errorText &&
        navegacion.errorText !== "ERR_ABORTED"
      ) {
        throw new Error(`No se pudo abrir ${paso.url}: ${navegacion.errorText}`);
      }
      if (paso.js) {
        const valor = await evaluar(socket, paso.js);
        if (valor === false) {
          throw new Error(`Falló la acción JS del paso "${paso.nombre}".`);
        }
      }
      if (paso.esperar) {
        const listo = await esperarSelector(
          socket,
          paso.esperar,
          paso.sin_texto || null,
          timeoutMs
        );
        if (!listo) {
          throw new Error(
            `Tiempo agotado esperando "${paso.esperar}" en "${paso.nombre}".`
          );
        }
      }
      await dormir(350);
      if (paso.captura) {
        const alto = await evaluar(
          socket,
          "Math.min(Math.max(document.documentElement.scrollHeight, 700), 4000)"
        );
        const captura = await enviar(socket, "Page.captureScreenshot", {
          format: "png",
          captureBeyondViewport: true,
          clip: { x: 0, y: 0, width: 1280, height: alto, scale: 1 },
        });
        writeFileSync(join(salida, paso.captura), Buffer.from(captura.data, "base64"));
        capturas.push(paso.captura);
        console.error(`  [ok] ${paso.nombre} → ${paso.captura}`);
      }
    }
    console.log(JSON.stringify({ capturas }));
    process.exit(0);
  } finally {
    try {
      socket.close();
    } catch (error) {
      /* nada que hacer */
    }
  }
}

principal().catch((error) => {
  console.log(
    JSON.stringify({ error: String(error.message || error), paso: "desconocido" })
  );
  process.exit(1);
});
