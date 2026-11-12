#!/usr/bin/env python3
"""Capturas de pantalla para el manual de usuario (Sprint 13.3).

Levanta el prototipo en un servidor local (puerto efímero), siembra el
escenario de demostración del manual (jugador, árbitro, admin y sus
combates) en la base de datos de desarrollo, abre Microsoft Edge headless
con puerto de depuración y toma las 11 capturas del manual con CDP
(``scripts/cdp_capturar.mjs``) en ``documentation/capturas/``.

La siembra es idempotente (claves de idempotencia por combate): se puede
repetir sin duplicar datos, de modo que las credenciales del manual siguen
válidas en ``instance/app.db`` para probar los pasos a mano.

Requisitos: un navegador Chromium/Edge y Node 18+ (en este entorno: el Edge
y el Node de Windows, igual que en ``verificar_admin_browser.py``). No
requiere que haya otro servidor en marcha.

Uso (desde la raíz del repo):

    venv/bin/python scripts/capturar_manual_usuario.py
    venv/bin/python scripts/capturar_manual_usuario.py --navegador ... --node ...

Los PNG resultantes se embeben en ``documentation/MANUAL_USUARIO.md``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "scripts"
sys.path.insert(0, str(RAIZ / "prototype"))
sys.path.insert(0, str(SCRIPTS))

from verificar_admin_browser import (  # noqa: E402  (tras ajustar sys.path)
    _detectar_navegador,
    _detectar_node,
    _perfil_temporal,
    _puerto_libre,
    _ruta_windows,
)

CAPTURAS = RAIZ / "documentation" / "capturas"
MJS = SCRIPTS / "cdp_capturar.mjs"
PLAN_TEMPORAL = CAPTURAS / "_plan.json"

# Credenciales del escenario (también documentadas en MANUAL_USUARIO.md).
PASSWORD = "password123"
USUARIOS = (
    ("carla@manual.local", "Carla Jugadora", "jugador"),
    ("luis@manual.local", "Luis Rival", "jugador"),
    ("marta@manual.local", "Marta Contrincante", "jugador"),
    ("nico@manual.local", "Nico Duelista", "jugador"),
    ("arturo@manual.local", "Arturo Árbitro", "arbitro"),
    ("ana@manual.local", "Ana Admin", "admin"),
)


def sembrar_escenario() -> None:
    """Crea (idempotente) los usuarios y combates del manual en la BD de desarrollo."""
    from app import create_app
    from app.extensions import db
    from app.modules.combat import services as combat_services
    from app.modules.combat.domain.estados import EstadoCombate
    from app.modules.iam import services as iam_services
    from app.modules.iam.models import Role
    from app.modules.iam.repositories import RoleRepository, UserRepository
    from app.shared.errors import ConflictError

    app = create_app()
    with app.app_context():
        db.create_all()
        for nombre in ("jugador", "arbitro", "admin", "super_admin"):
            if RoleRepository.get_by_name(nombre) is None:
                db.session.add(Role(name=nombre))
        db.session.commit()

        def usuario(email: str, nombre: str, rol: str):
            existente = UserRepository.get_by_email(email)
            if existente is not None:
                return existente
            creado = iam_services.register_user(
                email=email, password=PASSWORD, name=nombre, community_id=1
            )
            creado.role_id = RoleRepository.get_by_name(rol).id
            db.session.commit()
            return creado

        por_email = {
            email: usuario(email, nombre, rol) for email, nombre, rol in USUARIOS
        }
        carla = por_email["carla@manual.local"]
        luis = por_email["luis@manual.local"]
        marta = por_email["marta@manual.local"]
        nico = por_email["nico@manual.local"]
        arturo = por_email["arturo@manual.local"]

        ahora = datetime.now().replace(microsecond=0)

        def confirmar_si_falta(user_id: int, combate, ganador_id: int) -> None:
            try:
                combat_services.confirm_combat(
                    user_id=user_id,
                    combat_id=combate.id,
                    result={"winner_id": ganador_id},
                )
            except ConflictError:
                pass  # ya había confirmado en una corrida anterior

        def cerrado(a, b, ganador, dias: int, clave: str) -> None:
            combate, _ = combat_services.report_combat(
                reporter_id=a.id,
                participants=[a.id, b.id],
                winner=ganador.id,
                played_at=ahora - timedelta(days=dias),
                client_request_id=clave,
            )
            if combate.status is EstadoCombate.PENDIENTE:
                confirmar_si_falta(a.id, combate, ganador.id)
                confirmar_si_falta(b.id, combate, ganador.id)
            db.session.commit()
            if combate.status is not EstadoCombate.CONFIRMADO:
                raise RuntimeError(f"El combate {clave} no quedó CONFIRMADO.")

        # Cuatro combates cerrados: ranking poblado e historial de Carla.
        cerrado(luis, carla, luis, dias=30, clave="manual-c1-luis-carla")
        cerrado(carla, marta, carla, dias=21, clave="manual-c2-carla-marta")
        cerrado(nico, carla, carla, dias=14, clave="manual-c3-nico-carla")
        cerrado(carla, nico, nico, dias=7, clave="manual-c4-carla-nico")

        # Un conflicto para el panel de administración (confirmaciones distintas).
        conflicto, _ = combat_services.report_combat(
            reporter_id=marta.id,
            participants=[marta.id, nico.id],
            winner=marta.id,
            played_at=ahora - timedelta(days=3),
            client_request_id="manual-c5-conflicto",
        )
        if conflicto.status is EstadoCombate.PENDIENTE:
            confirmar_si_falta(marta.id, conflicto, marta.id)
            confirmar_si_falta(nico.id, conflicto, nico.id)
        db.session.commit()
        if conflicto.status is not EstadoCombate.CONFLICTO:
            raise RuntimeError("El combate de prueba no quedó en CONFLICTO.")

        # Un combate con árbitro asignado y sin confirmaciones: pendiente
        # a la vez para Carla (participante) y Arturo (árrbitro).
        reportado, _ = combat_services.report_combat(
            reporter_id=luis.id,
            participants=[luis.id, carla.id],
            winner=luis.id,
            played_at=ahora - timedelta(days=1),
            referee_id=arturo.id,
            client_request_id="manual-c6-arbitro",
        )
        db.session.commit()
        if reportado.status is not EstadoCombate.PENDIENTE:
            raise RuntimeError("El combate con árbitro no quedó PENDIENTE.")

        print(
            f"Escenario sembrado: {len(USUARIOS)} usuarios, 4 combates cerrados, "
            f"1 conflicto (#{conflicto.id}), 1 pendiente con árbitro (#{reportado.id})."
        )


def construir_plan(url_base: str) -> list[dict]:
    """Pasos de captura (11 PNG) con las sesiones del manual."""
    base = url_base.rstrip("/")

    def login(email: str) -> str:
        return (
            "fetch('/auth/login',{method:'POST',"
            "headers:{'Content-Type':'application/json'},"
            f"body:JSON.stringify({{email:{json.dumps(email)},"
            f"password:{json.dumps(PASSWORD)}}})"
            "}).then(r=>r.ok)"
        )

    def logout_login(email: str) -> str:
        return (
            "fetch('/auth/logout',{method:'POST'})"
            f".then(()=>{login(email)})"
        )

    return [
        {
            "nombre": "login-publico",
            "url": f"{base}/login",
            "esperar": "#email",
            "captura": "01-login.png",
        },
        {
            "nombre": "inicio-publico",
            "url": f"{base}/",
            "esperar": ".boton",
            "captura": "02-inicio.png",
        },
        {
            "nombre": "ranking-publico",
            "url": f"{base}/ranking",
            "esperar": "table.tabla tbody tr",
            "captura": "03-ranking.png",
        },
        {"nombre": "sesion-carla", "url": f"{base}/login", "js": login("carla@manual.local")},
        {
            "nombre": "reportar",
            "url": f"{base}/reportar",
            "esperar": "#lista-jugadores option",
            "captura": "04-reportar.png",
        },
        {
            "nombre": "pendientes-jugador",
            "url": f"{base}/pendientes",
            "esperar": "#lista-pendientes .tarjeta",
            "captura": "05-pendientes-jugador.png",
        },
        {
            "nombre": "historial",
            "url": f"{base}/historial",
            "esperar": "table.tabla tbody tr",
            "captura": "06-historial.png",
        },
        {
            "nombre": "cachear-lecturas",
            "url": f"{base}/ranking",
            "js": (
                "Promise.all(["
                "fetch('/api/ranking').then(r=>r.ok),"
                "fetch('/me/history').then(r=>r.ok)])"
            ),
        },
        {
            "nombre": "offline-copiado",
            "url": f"{base}/offline",
            "esperar": "#ranking-offline",
            "sin_texto": "Cargando",
            "captura": "07-offline.png",
        },
        {
            "nombre": "sesion-arturo",
            "url": f"{base}/login",
            "js": logout_login("arturo@manual.local"),
        },
        {
            "nombre": "pendientes-arbitro",
            "url": f"{base}/pendientes",
            "esperar": "#lista-pendientes .tarjeta",
            "captura": "08-pendientes-arbitro.png",
        },
        {"nombre": "sesion-ana", "url": f"{base}/login", "js": logout_login("ana@manual.local")},
        {
            "nombre": "admin-portada",
            "url": f"{base}/admin",
            "esperar": "#btn-recalcular",
            "captura": "09-admin-portada.png",
        },
        {
            "nombre": "admin-usuarios",
            "url": f"{base}/admin/panel/usuarios",
            "esperar": "table.tabla tbody tr",
            "captura": "10-admin-usuarios.png",
        },
        {
            "nombre": "admin-combates",
            "url": f"{base}/admin/panel/combates",
            "esperar": "#lista-combates .tarjeta",
            "captura": "11-admin-combates.png",
        },
    ]


def levantar_servidor():
    """Arranca el prototipo en un puerto efímero de 127.0.0.1 (hilo propio)."""
    from werkzeug.serving import make_server

    from app import create_app

    app = create_app()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    servidor = make_server("127.0.0.1", puerto, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return servidor, f"http://127.0.0.1:{puerto}"


def capturar(url_base: str, navegador: str, node: str, timeout: int) -> list[str]:
    """Ejecuta Edge headless + el capturador CDP y devuelve los PNG obtenidos."""
    if not MJS.exists():
        raise FileNotFoundError(f"No se encuentra el capturador CDP: {MJS}")

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    plan = construir_plan(url_base)
    PLAN_TEMPORAL.write_text(json.dumps(plan, ensure_ascii=True), encoding="utf-8")

    puerto = _puerto_libre()
    perfil = _perfil_temporal()
    proceso = subprocess.Popen(
        [
            navegador,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
            "--disable-extensions",
            "--hide-scrollbars",
            "--window-size=1280,900",
            f"--user-data-dir={_ruta_windows(perfil)}",
            f"--remote-debugging-port={puerto}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        resultado = subprocess.run(
            [
                node,
                _ruta_windows(str(MJS)),
                "--port",
                str(puerto),
                "--plan",
                _ruta_windows(str(PLAN_TEMPORAL)),
                "--salida",
                _ruta_windows(str(CAPTURAS)),
                "--timeout-ms",
                "25000",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        salida = (resultado.stdout or "").strip().splitlines()
        ultimo = salida[-1] if salida else ""
        try:
            datos = json.loads(ultimo)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Salida inesperada del capturador CDP.\n"
                f"stdout: {resultado.stdout[:600]}\nstderr: {resultado.stderr[:600]}"
            ) from exc
        if resultado.returncode != 0 or "error" in datos:
            raise RuntimeError(
                f"Falló la captura: {datos.get('error', 'error desconocido')}\n"
                f"stderr: {resultado.stderr[:600]}"
            )
        return list(datos.get("capturas", []))
    finally:
        PLAN_TEMPORAL.unlink(missing_ok=True)
        proceso.terminate()
        try:
            proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proceso.kill()
        shutil.rmtree(perfil, ignore_errors=True)


def verificar(planes: list[dict], capturados: list[str]) -> None:
    """Comprueba que cada PNG del plan exista en disco y no esté vacío."""
    fallas = []
    for paso in planes:
        nombre = paso.get("captura")
        if not nombre:
            continue
        archivo = CAPTURAS / nombre
        if nombre not in capturados:
            fallas.append(f"{nombre}: no lo reportó el navegador")
        elif not archivo.exists() or archivo.stat().st_size < 1000:
            fallas.append(f"{nombre}: archivo ausente o vacío")
        else:
            print(f"  {nombre}  ({archivo.stat().st_size // 1024} KiB)")
    if fallas:
        raise RuntimeError("Capturas incompletas:\n  " + "\n  ".join(fallas))


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--navegador", default=None)
    analizador.add_argument("--node", default=None)
    analizador.add_argument("--timeout", type=int, default=300)
    argumentos = analizador.parse_args()

    navegador = argumentos.navegador or _detectar_navegador()
    if not navegador:
        print(
            "No se encontró un navegador Chromium/Edge. Indícalo con "
            "--navegador /ruta/al/navegador.",
            file=sys.stderr,
        )
        return 1
    node = argumentos.node or _detectar_node()
    if not node:
        print("No se encontró Node. Indícalo con --node /ruta/al/node.", file=sys.stderr)
        return 1

    print(f"Navegador: {navegador}")
    print(f"Node: {node}")

    sembrar_escenario()
    servidor, url_base = levantar_servidor()
    print(f"Servidor local: {url_base}")
    try:
        capturados = capturar(url_base, navegador, node, argumentos.timeout)
        plan = construir_plan(url_base)
        verificar(plan, capturados)
    finally:
        servidor.shutdown()
        servidor.server_close()

    print(f"Listo: {len(capturados)} capturas en {CAPTURAS.relative_to(RAIZ)}/")
    print("Embébelas en documentation/MANUAL_USUARIO.md (tarea 13.3).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — punto único de fallo del script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
