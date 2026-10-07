"""Casos de uso combate: aggregate, máquina de estados, prioridad de árbitro, auditoría.

Sprint 4: registro de un combate con todas las validaciones de dominio.
Sprint 5: confirmaciones de participantes/árbitro (5.2), auditoría de ediciones
admin (5.3) y edición manual del resultado (5.4). Las transiciones de estado
viven en ``domain/estados.py`` (puro).
"""

from datetime import datetime, timezone

from app.modules.combat.domain.estados import (
    EstadoCombate,
    ResultadoParticipante,
    transicionar,
)
from app.modules.combat.models import (
    Combat,
    CombatParticipant,
    Confirmation,
)
from app.modules.combat.repositories import (
    ConfirmationRepository,
    CombatRepository,
)
from app.modules.iam.repositories import UserRepository
from app.shared.errors import ConflictError, DomainError, NotFoundError

# Roles que pueden actuar como árbitro (tabla `roles` fija del MVP: 4.3).
ROLES_ARBITRO = frozenset({"arbitro", "admin", "super_admin"})

# Un combate de ranking individual enfrenta a exactamente dos jugadores
# (Art. 30 está dentro de la REGLA 6 — modalidad individual).
PARTICIPANTES_REQUERIDOS = 2

_CLIENTE_MAX = 64  # longitud máxima de client_request_id


def _utc_ahora() -> datetime:
    """Ahora en UTC como datetime naive (SQLite no almacena husos)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalizar_fecha(valor) -> datetime:
    """Convierte la fecha de juego a UTC naive.

    Acepta ``datetime`` o string ISO-8601 (``"2026-10-06T18:30:00"`` o con
    ``Z``/offset). Lanza DomainError si el formato no es interpretable.
    """
    if isinstance(valor, datetime):
        fecha = valor
    elif isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            raise DomainError("La fecha del combate es obligatoria.")
        try:
            fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DomainError(
                "La fecha del combate debe ser una fecha ISO-8601 válida."
            ) from exc
    else:
        raise DomainError("La fecha del combate es obligatoria.")

    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    return fecha


def _usuario_o_error(user_id, campo: str):
    """Resuelve un usuario existente o lanza NotFoundError."""
    if user_id is None:
        raise DomainError(f"El campo '{campo}' es obligatorio.")
    try:
        identificador = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DomainError(f"El campo '{campo}' debe ser un identificador numérico.") from exc
    usuario = UserRepository.get_by_id(identificador)
    if usuario is None:
        raise NotFoundError(f"No existe el usuario {identificador} referenciado en '{campo}'.")
    return usuario


def _ids_participantes(participants) -> list[int]:
    """Valida la lista de participantes: exactamente 2 y distintos.

    Acepta lista/tupla de ids o, para los formularios web, una cadena
    separada por comas (``"3,7"``).
    """
    if isinstance(participants, str):
        participants = [p.strip() for p in participants.split(",") if p.strip()]
    if not isinstance(participants, (list, tuple, set)):
        raise DomainError("'participants' debe ser una lista de identificadores.")
    try:
        ids = [int(pid) for pid in participants]
    except (TypeError, ValueError) as exc:
        raise DomainError("'participants' debe contener solo identificadores numéricos.") from exc

    if len(ids) != PARTICIPANTES_REQUERIDOS:
        raise DomainError(
            f"Un combate individual tiene exactamente {PARTICIPANTES_REQUERIDOS} "
            f"participantes (recibidos: {len(ids)})."
        )
    if len(set(ids)) != len(ids):
        raise DomainError("Los participantes deben ser dos personas distintas.")
    return ids


def report_combat(
    reporter_id,
    participants,
    winner,
    played_at,
    referee_id=None,
    client_request_id=None,
) -> tuple[Combat, bool]:
    """Registra un combate nuevo en estado ``PENDIENTE`` (RF6).

    Args:
        reporter_id: quién envía el reporte (participante o árbitro).
        participants: lista con los ids de los **2** participantes.
        winner: id del ganador, que debe ser uno de los participantes.
        played_at: fecha de juego (``datetime`` o string ISO-8601), no futura.
        referee_id: árbitro asignado (opcional; debe tener rol de árbitro).
        client_request_id: clave de idempotencia por emisor (opcional, ≤64
            caracteres) para que los reenvíos offline no dupliquen el combate.

    Returns:
        ``(combat, creado)`` — ``creado`` es ``False`` cuando la clave de
        idempotencia ya existía: se devuelve el combate original sin crear
        otro ni producir ningún efecto secundario.

    Raises:
        NotFoundError: usuario referenciado inexistente (404).
        DomainError: cualquier validación de dominio fallida (400).
    """
    ids = _ids_participantes(participants)

    reporter = _usuario_o_error(reporter_id, "reporter_id")
    participantes = [_usuario_o_error(pid, "participants") for pid in ids]

    # Mismo community_id en todo el reporte (RNF006 + aislamiento de datos).
    community_id = reporter.community_id
    for usuario in participantes:
        if usuario.community_id != community_id:
            raise DomainError(
                "Todos los participantes deben pertenecer a la misma comunidad "
                f"que quien reporta (comunidad {community_id})."
            )

    # El reporter participa o es árbitro.
    if reporter.id not in ids and reporter.role.name not in ROLES_ARBITRO:
        raise DomainError("Solo puede reportar un combate un participante o un árbitro.")

    # Árbitro asignado: existe, misma comunidad y rol habilitado.
    arbitro = None
    if referee_id not in (None, ""):
        arbitro = _usuario_o_error(referee_id, "referee_id")
        if arbitro.community_id != community_id:
            raise DomainError("El árbitro debe pertenecer a la misma comunidad.")
        if arbitro.role.name not in ROLES_ARBITRO:
            raise DomainError("El usuario indicado como árbitro no tiene rol de árbitro.")

    # El ganador debe ser uno de los participantes.
    try:
        ganador_id = int(winner)
    except (TypeError, ValueError) as exc:
        raise DomainError("El campo 'winner' debe ser un identificador numérico.") from exc
    if ganador_id not in ids:
        raise DomainError("El ganador declarado no es uno de los participantes del combate.")

    # Fecha de juego no futura.
    fecha = _normalizar_fecha(played_at)
    if fecha > _utc_ahora():
        raise DomainError("La fecha del combate no puede estar en el futuro.")

    # Clave de idempotencia: si ya existe, no se crea nada nuevo (RF5).
    clave = (client_request_id or "").strip() or None
    if clave is not None:
        if len(clave) > _CLIENTE_MAX:
            raise DomainError(
                f"'client_request_id' no puede superar {_CLIENTE_MAX} caracteres."
            )
        existente = CombatRepository.get_by_idempotency_key(
            community_id, reporter.id, clave
        )
        if existente is not None:
            return existente, False

    combate = Combat(
        community_id=community_id,
        reporter_id=reporter.id,
        referee_id=arbitro.id if arbitro else None,
        status=EstadoCombate.PENDIENTE,
        played_at=fecha,
        client_request_id=clave,
        processed=False,
    )
    for usuario in participantes:
        combate.participants.append(
            CombatParticipant(
                user_id=usuario.id,
                result=(
                    ResultadoParticipante.VICTORIA
                    if usuario.id == ganador_id
                    else ResultadoParticipante.DERROTA
                ),
                community_id=community_id,
            )
        )

    CombatRepository.add(combate)
    CombatRepository.save()
    return combate, True


def _ganador_reportado(result, combate: Combat) -> int:
    """Extrae y valida el id del ganador que declara el confirmador.

    Args:
        result: resultado reportado — ``{"winner_id": n}``, ``{"winner": n}``
            o el id directamente (los formularios envían un campo suelto).
        combate: combate en curso (para validar que sea un participante).

    Returns:
        id del participante que este confirmador declara ganador.

    Raises:
        DomainError: campo ausente, no numérico o que no es un participante.
    """
    valor = result.get("winner_id", result.get("winner")) if isinstance(result, dict) else result
    if valor is None or valor == "":
        raise DomainError("El campo 'winner_id' es obligatorio.")
    try:
        ganador_id = int(valor)
    except (TypeError, ValueError) as exc:
        raise DomainError("El campo 'winner_id' debe ser un identificador numérico.") from exc

    ids = combate.participante_ids
    if ganador_id not in ids:
        raise DomainError(
            f"'winner_id' debe ser uno de los participantes del combate "
            f"({', '.join(str(i) for i in ids)})."
        )
    return ganador_id


def _cerrar_confirmado(combate: Combat, ganador_id: int) -> None:
    """Cierra el combate en ``CONFIRMADO`` alineando el resultado declarado.

    El resultado confirmado es el que manda: se reescribe ``result`` de cada
    participante para que el aggregate quede coherente antes del recálculo Elo.

    HOOK SPRINT 6: al pasar a un estado terminal (CONFIRMADO/RESUELTO) es
    donde entra el recálculo on-write del ranking (ranking.services).
    """
    for participante in combate.participants:
        participante.result = (
            ResultadoParticipante.VICTORIA
            if participante.user_id == ganador_id
            else ResultadoParticipante.DERROTA
        )
    combate.status = transicionar(combate.status, EstadoCombate.CONFIRMADO)


def confirm_combat(user_id, combat_id, result) -> Combat:
    """Registra la confirmación de un combate (RF8).

    Reglas de dominio:

    - Solo puede confirmar un **participante** o el **árbitro asignado**.
    - Cada usuario confirma **una sola vez** (reenvíos → 409).
    - Dos participantes con el mismo ganador declarado → ``CONFIRMADO``.
    - Dos participantes con ganadores distintos → ``CONFLICTO``.
    - La confirmación del **árbitro asignado** cierra en ``CONFIRMADO``
      inmediatamente y **prevalece** sobre lo que hayan declarado los
      participantes (RF8: en conflicto prevalece el árbitro).

    Args:
        user_id: quién confirma.
        combat_id: combate a confirmar.
        result: resultado reportado (``{"winner_id": n}`` o el id del ganador).

    Returns:
        El combate con su nuevo estado.

    Raises:
        NotFoundError: combate o usuario inexistentes (404).
        ConflictError: este usuario ya había confirmado (409).
        DomainError: combate cerrado, quien confirma sin derecho, o
            ``winner_id`` que no es un participante (400).
    """
    combate = CombatRepository.get_by_id(combat_id)
    if combate is None:
        raise NotFoundError(f"No existe el combate {combat_id}.")

    confirmador = _usuario_o_error(user_id, "user_id")

    if combate.status not in (EstadoCombate.PENDIENTE, EstadoCombate.CONFLICTO):
        raise DomainError(
            f"El combate {combate.id} ya está cerrado (estado "
            f"{combate.status.value}): no admite más confirmaciones."
        )

    es_arbitro = combate.referee_id == confirmador.id
    ids = combate.participante_ids
    if not es_arbitro and confirmador.id not in ids:
        raise DomainError("Solo puede confirmar el combate un participante o el árbitro asignado.")

    if ConfirmationRepository.get(combate.id, confirmador.id) is not None:
        raise ConflictError(f"El usuario {confirmador.id} ya confirmó el combate {combate.id}.")

    ganador_id = _ganador_reportado(result, combate)
    ConfirmationRepository.add(
        Confirmation(
            combat_id=combate.id,
            user_id=confirmador.id,
            reported_result={"winner_id": ganador_id},
            community_id=combate.community_id,
        )
    )

    if es_arbitro:
        # Prioridad del árbitro: cierra el combate con lo que él declare.
        _cerrar_confirmado(combate, ganador_id)
    elif combate.status is EstadoCombate.PENDIENTE:
        confirmaciones = [
            c
            for c in ConfirmationRepository.confirmaciones_de(combate.id)
            if c.user_id in ids
        ]
        if len(confirmaciones) == PARTICIPANTES_REQUERIDOS:
            ganadores = {c.ganador_id for c in confirmaciones}
            if len(ganadores) == 1:
                _cerrar_confirmado(combate, ganador_id)
            else:
                combate.status = transicionar(combate.status, EstadoCombate.CONFLICTO)

    CombatRepository.save()
    return combate

