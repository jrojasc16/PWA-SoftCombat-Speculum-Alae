"""Tests del módulo combate (Sprint 4.6).

Cubre las tres áreas que pide el plan:
1. Validaciones de dominio del registro (``services.report_combat``).
2. Máquina de estados (dominio puro, tarea 4.2).
3. Idempotencia del reporte por ``client_request_id`` (tarea 4.5).

Y el recorrido HTTP de las rutas del blueprint (404/401/200/201).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services
from app.modules.combat.domain.estados import (
    EstadoCombate,
    ResultadoParticipante,
    es_terminal,
    puede_transicionar,
    transiciones_permitidas,
    transicionar,
)
from app.modules.combat.models import Combat
from app.modules.combat.repositories import CombatRepository
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.shared.errors import DomainError, NotFoundError

AYER = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)


def _usuario(email: str, nombre: str, rol: str = "jugador", comunidad: int = 1):
    """Crea un usuario con hash real y le asigna el rol indicado."""
    user = iam_services.register_user(
        email=email, password="password123", name=nombre, community_id=comunidad
    )
    user.role_id = RoleRepository.get_by_name(rol).id
    db.session.commit()
    return user


@pytest.fixture
def escenario(roles):
    """Dos jugadores (ana/beto) y un árbitro (caro) en la comunidad 1."""
    ana = _usuario("ana@x.com", "Ana Rojas")
    beto = _usuario("beto@x.com", "Beto Sanz")
    caro = _usuario("caro@x.com", "Caro Diaz", rol="arbitro")
    return {"ana": ana, "beto": beto, "caro": caro}


def _reportar(reporter, participantes, ganador, fecha=AYER, **extra):
    """Atajo para llamar al servicio con los ids del escenario."""
    return services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=fecha,
        **extra,
    )


# ---------------------------------------------------------------------------
# 1. Máquina de estados (dominio puro)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "origen, destino",
    [
        (EstadoCombate.PENDIENTE, EstadoCombate.CONFIRMADO),
        (EstadoCombate.PENDIENTE, EstadoCombate.CONFLICTO),
        (EstadoCombate.PENDIENTE, EstadoCombate.RESUELTO),
        (EstadoCombate.CONFLICTO, EstadoCombate.CONFIRMADO),
        (EstadoCombate.CONFLICTO, EstadoCombate.RESUELTO),
        (EstadoCombate.CONFIRMADO, EstadoCombate.RESUELTO),
    ],
)
def test_transiciones_permitidas(origen, destino):
    """Los seis caminos documentados en la máquina de estados son válidos."""
    assert puede_transicionar(origen, destino)
    assert transicionar(origen, destino) is destino


@pytest.mark.parametrize(
    "origen, destino",
    [
        (EstadoCombate.RESUELTO, EstadoCombate.CONFIRMADO),
        (EstadoCombate.RESUELTO, EstadoCombate.PENDIENTE),
        (EstadoCombate.RESUELTO, EstadoCombate.CONFLICTO),
        (EstadoCombate.CONFIRMADO, EstadoCombate.PENDIENTE),
        (EstadoCombate.CONFIRMADO, EstadoCombate.CONFLICTO),
        (EstadoCombate.CONFLICTO, EstadoCombate.PENDIENTE),
        (EstadoCombate.PENDIENTE, EstadoCombate.PENDIENTE),
    ],
)
def test_transiciones_rechazadas(origen, destino):
    """Las transiciones inversas o repetidas se rechazan explícitamente."""
    assert not puede_transicionar(origen, destino)
    with pytest.raises(ValueError, match="Transición inválida"):
        transicionar(origen, destino)


def test_resuelto_es_estado_terminal():
    """RESUELTO no admite ninguna transición posterior."""
    assert es_terminal(EstadoCombate.RESUELTO)
    assert transiciones_permitidas(EstadoCombate.RESUELTO) == frozenset()
    assert not es_terminal(EstadoCombate.PENDIENTE)


def test_estado_desconocido_lanza_error():
    """Cualquier valor fuera de los cuatro estados es inválido."""
    with pytest.raises(ValueError):
        transiciones_permitidas("INVENTADO")
    assert not puede_transicionar(EstadoCombate.PENDIENTE, "INVENTADO")


# ---------------------------------------------------------------------------
# 2. Validaciones del registro de un combate
# ---------------------------------------------------------------------------


def test_reporte_valido_queda_pendiente(escenario):
    """Registro correcto: estado PENDIENTE, 2 participantes y ganador marcado."""
    ana, beto = escenario["ana"], escenario["beto"]
    combate, creado = _reportar(ana, [ana, beto], ana)
    assert creado is True
    assert combate.id is not None
    assert combate.status is EstadoCombate.PENDIENTE
    assert combate.processed is False
    assert combate.reporter_id == ana.id
    assert combate.referee_id is None
    assert combate.participante_ids == [ana.id, beto.id]
    assert combate.ganador_id == ana.id
    assert combate.community_id == 1
    assert combate.participants[0].result is ResultadoParticipante.VICTORIA
    assert combate.participants[1].result is ResultadoParticipante.DERROTA


def test_reporte_con_arbitro_asignado(escenario):
    """El árbitro asignado se persiste y los participantes conservan el orden."""
    ana, beto, caro = escenario["ana"], escenario["beto"], escenario["caro"]
    combate, _ = _reportar(caro, [beto, ana], beto, referee_id=caro.id)
    assert combate.referee_id == caro.id
    assert combate.participante_ids == [beto.id, ana.id]
    assert combate.ganador_id == beto.id


@pytest.mark.parametrize("participantes", [[], [1], [1, 2, 3]])
def test_reporte_exige_dos_participantes(escenario, participantes):
    """Art. 30 (modalidad individual): exactamente 2 participantes."""
    ana = escenario["ana"]
    with pytest.raises(DomainError, match="exactamente 2 participantes"):
        services.report_combat(
            reporter_id=ana.id,
            participants=participantes,
            winner=ana.id,
            played_at=AYER,
        )


def test_reporte_rechaza_participantes_repetidos(escenario):
    """Los dos participantes deben ser personas distintas."""
    ana = escenario["ana"]
    with pytest.raises(DomainError, match="dos personas distintas"):
        _reportar(ana, [ana, ana], ana)


@pytest.mark.parametrize(
    "participantes",
    [
        ["no-es-lista"],
        [[1, 2]],
        ["x", "y"],
        None,
    ],
)
def test_reporte_rechaza_participantes_mal_formados(escenario, participantes):
    """'participants' debe ser una lista de identificadores numéricos."""
    ana = escenario["ana"]
    with pytest.raises(DomainError, match="participants"):
        services.report_combat(
            reporter_id=ana.id,
            participants=participantes,
            winner=ana.id,
            played_at=AYER,
        )


def test_reporte_rechaza_participante_inexistente(escenario):
    """Referenciar un usuario que no existe responde 404."""
    ana, beto = escenario["ana"], escenario["beto"]
    with pytest.raises(NotFoundError):
        services.report_combat(
            reporter_id=ana.id,
            participants=[ana.id, 99999],
            winner=ana.id,
            played_at=AYER,
        )


def test_reporte_rechaza_reporter_ajeno(escenario):
    """Solo puede reportar un participante o un árbitro."""
    ajeno = _usuario("ajeno@x.com", "Ajeno Perez")
    ana, beto = escenario["ana"], escenario["beto"]
    assert ajeno.id not in (ana.id, beto.id)
    with pytest.raises(DomainError, match="un participante o un árbitro"):
        _reportar(ajeno, [ana, beto], ana)


def test_arbitro_puede_reportar_sin_participar(escenario):
    """El árbitro asignado no participa pero sí puede reportar."""
    ana, beto, caro = escenario["ana"], escenario["beto"], escenario["caro"]
    combate, creado = _reportar(caro, [ana, beto], ana, referee_id=caro.id)
    assert creado and combate.reporter_id == caro.id


def test_reporte_rechaza_ganador_fuera_de_participantes(escenario):
    """El ganador declarado debe ser uno de los dos luchadores."""
    ana, beto = escenario["ana"], escenario["beto"]
    tercero = _usuario("tercero@x.com", "Tercero Diaz")
    with pytest.raises(DomainError, match="no es uno de los participantes"):
        _reportar(ana, [ana, beto], tercero)


def test_reporte_rechaza_fecha_futura(escenario):
    """La fecha de juego no puede estar en el futuro."""
    ana, beto = escenario["ana"], escenario["beto"]
    futuro = datetime.now(timezone.utc) + timedelta(hours=1)
    with pytest.raises(DomainError, match="no puede estar en el futuro"):
        _reportar(ana, [ana, beto], ana, fecha=futuro)


def test_reporte_rechaza_fecha_invalida(escenario):
    """Cualquier texto que no sea ISO-8601 válido se rechaza."""
    ana, beto = escenario["ana"], escenario["beto"]
    with pytest.raises(DomainError, match="ISO-8601"):
        _reportar(ana, [ana, beto], ana, fecha="ayer por la tarde")
    with pytest.raises(DomainError, match="obligatoria"):
        _reportar(ana, [ana, beto], ana, fecha="")


def test_reporte_acepta_fecha_iso_y_datetime(escenario):
    """Se acepta string ISO-8601 (con y sin offset) y datetime con tz."""
    ana, beto = escenario["ana"], escenario["beto"]
    c1, _ = _reportar(ana, [ana, beto], ana, fecha="2026-10-01T18:30:00")
    assert c1.played_at == datetime(2026, 10, 1, 18, 30)
    c2, _ = _reportar(
        ana, [ana, beto], beto, fecha="2026-10-01T20:00:00Z"
    )
    assert c2.played_at == datetime(2026, 10, 1, 20, 0)
    c3, _ = _reportar(
        ana,
        [ana, beto],
        ana,
        fecha=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
    )
    assert c3.played_at == datetime(2026, 10, 2, 10, 0)


def test_reporte_rechaza_comunidades_distintas(escenario):
    """Todos los involucrados deben compartir comunidad (RNF006)."""
    ana, beto = escenario["ana"], escenario["beto"]
    fuera = _usuario("fuera@x.com", "Fuera Lopez", comunidad=2)
    with pytest.raises(DomainError, match="misma comunidad"):
        services.report_combat(
            reporter_id=ana.id,
            participants=[ana.id, fuera.id],
            winner=ana.id,
            played_at=AYER,
        )
    with pytest.raises(DomainError, match="misma comunidad"):
        _reportar(ana, [ana, beto], ana, referee_id=fuera.id)


def test_reporte_rechaza_arbitro_sin_rol(escenario):
    """Un jugador no puede designarse como árbitro."""
    ana, beto = escenario["ana"], escenario["beto"]
    with pytest.raises(DomainError, match="no tiene rol de árbitro"):
        _reportar(ana, [ana, beto], ana, referee_id=beto.id)


@pytest.mark.parametrize(
    "reporter_id, participantes, winner",
    [
        (None, None, None),
        ("texto", None, None),
        (99999, None, None),
    ],
)
def test_reporte_valida_el_reporter(escenario, reporter_id, participantes, winner):
    """El emisor debe existir y ser numérico."""
    ana, beto = escenario["ana"], escenario["beto"]
    with pytest.raises((DomainError, NotFoundError)):
        services.report_combat(
            reporter_id=reporter_id,
            participants=participantes if participantes is not None else [ana.id, beto.id],
            winner=winner if winner is not None else ana.id,
            played_at=AYER,
        )


def test_reporte_rechaza_winner_no_numerico(escenario):
    """'winner' debe ser un identificador numérico."""
    ana, beto = escenario["ana"], escenario["beto"]
    with pytest.raises(DomainError, match="winner"):
        services.report_combat(
            reporter_id=ana.id,
            participants=[ana.id, beto.id],
            winner=None,
            played_at=AYER,
        )


# ---------------------------------------------------------------------------
# 3. Idempotencia del reporte (client_request_id)
# ---------------------------------------------------------------------------


def test_reenvio_con_la_misma_clave_no_duplica(escenario):
    """El mismo client_request_id devuelve el combate original (creado=False)."""
    ana, beto = escenario["ana"], escenario["beto"]
    primero, creado1 = _reportar(
        ana, [ana, beto], ana, client_request_id="offline-abc-123"
    )
    segundo, creado2 = _reportar(
        ana, [ana, beto], ana, client_request_id="offline-abc-123"
    )
    assert creado1 is True and creado2 is False
    assert segundo.id == primero.id
    assert (
        db.session.execute(db.select(db.func.count()).select_from(Combat)).scalar() == 1
    )


def test_claves_distintas_creen_combates_distintos(escenario):
    """La idempotencia es por clave: otra clave sí crea otro combate."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar(ana, [ana, beto], ana, client_request_id="clave-1")
    _reportar(ana, [ana, beto], beto, client_request_id="clave-2")
    assert (
        db.session.execute(db.select(db.func.count()).select_from(Combat)).scalar() == 2
    )


def test_sin_clave_se_permite_repetir(escenario):
    """Sin client_request_id no hay restricción de unicidad."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar(ana, [ana, beto], ana)
    _reportar(ana, [ana, beto], ana)
    assert (
        db.session.execute(db.select(db.func.count()).select_from(Combat)).scalar() == 2
    )


def test_clave_en_blanco_se_trata_como_ausente(escenario):
    """Espacios en blanco o cadena vacía equivalen a no enviar clave."""
    ana, beto = escenario["ana"], escenario["beto"]
    c1, creado1 = _reportar(ana, [ana, beto], ana, client_request_id="   ")
    c2, creado2 = _reportar(ana, [ana, beto], ana, client_request_id="")
    assert creado1 and creado2
    assert c1.id != c2.id


def test_clave_demasiado_larga_se_rechaza(escenario):
    """Longitud máxima de client_request_id: 64 caracteres."""
    ana, beto = escenario["ana"], escenario["beto"]
    with pytest.raises(DomainError, match="64"):
        _reportar(ana, [ana, beto], ana, client_request_id="x" * 65)


def test_clave_diferente_emisor_no_colisiona(escenario, roles):
    """La unicidad es (comunidad, emisor, clave): otro emisor reutiliza la clave."""
    ana, beto = escenario["ana"], escenario["beto"]
    c1, _ = _reportar(ana, [ana, beto], ana, client_request_id="misma-clave")
    c2, creado2 = _reportar(beto, [ana, beto], beto, client_request_id="misma-clave")
    assert creado2 is True and c2.id != c1.id
    assert CombatRepository.get_by_idempotency_key(1, ana.id, "misma-clave").id == c1.id


# ---------------------------------------------------------------------------
# 4. Rutas HTTP del blueprint
# ---------------------------------------------------------------------------


def _login(client, usuario):
    """Inicia sesión con las credenciales fijas de _usuario()."""
    respuesta = client.post(
        "/auth/login", json={"email": usuario.email, "password": "password123"}
    )
    assert respuesta.status_code == 200
    return respuesta


def test_post_combats_requiere_sesion(client, escenario):
    """Sin sesión la API responde 401 (nunca redirige)."""
    ana, beto = escenario["ana"], escenario["beto"]
    r = client.post(
        "/combats",
        json={
            "participants": [ana.id, beto.id],
            "winner": ana.id,
            "played_at": "2026-10-01T18:30:00",
        },
    )
    assert r.status_code == 401
    assert r.get_json() == {"error": "Autenticación requerida."}


def test_post_combats_crea_y_consulta(client, escenario):
    """POST crea (201) y GET /combats/<id> devuelve el detalle (200)."""
    ana, beto = escenario["ana"], escenario["beto"]
    _login(client, ana)
    r = client.post(
        "/combats",
        json={
            "participants": [ana.id, beto.id],
            "winner": beto.id,
            "played_at": "2026-10-01T18:30:00",
        },
    )
    assert r.status_code == 201
    cuerpo = r.get_json()
    assert cuerpo["status"] == "PENDIENTE"
    assert cuerpo["processed"] is False
    assert [p["result"] for p in cuerpo["participants"]] == ["DERROTA", "VICTORIA"]

    detalle = client.get(f"/combats/{cuerpo['id']}")
    assert detalle.status_code == 200
    assert detalle.get_json()["id"] == cuerpo["id"]


def test_post_combats_reenvio_devuelve_200(client, escenario):
    """El reenvío idempotente responde 200 con el combate original."""
    ana, beto = escenario["ana"], escenario["beto"]
    _login(client, ana)
    payload = {
        "participants": [ana.id, beto.id],
        "winner": ana.id,
        "played_at": "2026-10-01T18:30:00",
        "client_request_id": "clave-reintento-1",
    }
    primero = client.post("/combats", json=payload)
    segundo = client.post("/combats", json=payload)
    assert primero.status_code == 201
    assert segundo.status_code == 200
    assert segundo.get_json()["id"] == primero.get_json()["id"]
    assert (
        db.session.execute(db.select(db.func.count()).select_from(Combat)).scalar() == 1
    )


def test_post_combats_acepta_formulario_web(client, escenario):
    """Los flujos de la PWA envían formularios: participants en "3,7"."""
    ana, beto = escenario["ana"], escenario["beto"]
    _login(client, ana)
    r = client.post(
        "/combats",
        data={
            "participants": f"{ana.id},{beto.id}",
            "winner": ana.id,
            "played_at": "2026-10-01T18:30:00",
        },
    )
    assert r.status_code == 201
    assert r.get_json()["status"] == "PENDIENTE"


def test_post_combats_formulario_participants_invalido(client, escenario):
    """Una cadena no numérica en el formulario devuelve 400 con el contrato."""
    ana, beto = escenario["ana"], escenario["beto"]
    _login(client, ana)
    r = client.post(
        "/combats",
        data={"participants": "uno,dos", "winner": ana.id, "played_at": "2026-10-01"},
    )
    assert r.status_code == 400
    assert "participants" in r.get_json()["error"]


def test_get_pending_lista_los_mios(client, escenario):
    """Cada participante ve en /combats/pending los combates por confirmar."""
    ana, beto, caro = escenario["ana"], escenario["beto"], escenario["caro"]
    _login(client, ana)
    r = client.post(
        "/combats",
        json={
            "participants": [ana.id, beto.id],
            "winner": ana.id,
            "played_at": "2026-10-01T18:30:00",
            "referee_id": caro.id,
        },
    )
    assert r.status_code == 201
    combate_id = r.get_json()["id"]

    assert client.get("/combats/pending").get_json()[0]["id"] == combate_id

    # beto (participante) también lo ve; un ajeno no.
    client.post("/auth/logout")
    _login(client, beto)
    assert client.get("/combats/pending").get_json()[0]["id"] == combate_id
    client.post("/auth/logout")

    ajeno = _usuario("ajeno2@x.com", "Ajeno Dos")
    _login(client, ajeno)
    assert client.get("/combats/pending").get_json() == []


def test_get_combat_inexistente_404(client, escenario):
    """Un id inexistente responde 404 con el contrato JSON de errores."""
    ana = escenario["ana"]
    _login(client, ana)
    r = client.get("/combats/99999")
    assert r.status_code == 404
    assert "No existe el combate" in r.get_json()["error"]


def test_get_pending_sin_sesion_401(client, escenario):
    """Los endpoints JSON nunca redirigen: responden 401."""
    assert client.get("/combats/pending").status_code == 401
    assert client.get("/combats/1").status_code == 401
