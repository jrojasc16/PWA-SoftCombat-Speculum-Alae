"""Casos de uso combate: aggregate, máquina de estados, prioridad de árbitro, auditoría.

Sprint 4: registro de un combate con todas las validaciones de dominio.
Sprint 5: confirmaciones de participantes/árbitro (5.2), auditoría de ediciones
admin (5.3) y edición manual del resultado (5.4). Las transiciones de estado
viven en ``domain/estados.py`` (puro).
"""

from collections.abc import Mapping
from datetime import datetime, timezone

from app.modules.combat.domain.estados import (
    EstadoCombate,
    ResultadoParticipante,
    transicionar,
)
from app.modules.combat.models import (
    AuditLog,
    Combat,
    CombatParticipant,
    Confirmation,
)
from app.modules.combat.repositories import (
    AuditLogRepository,
    ConfirmationRepository,
    CombatRepository,
)
from app.modules.iam.repositories import UserRepository
from app.shared.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)

# Roles que pueden actuar como árbitro (tabla `roles` fija del MVP: 4.3).
ROLES_ARBITRO = frozenset({"arbitro", "admin", "super_admin"})
# Roles que pueden editar resultados a mano (RBAC del MVP: 2 estados de roles).
ROLES_ADMIN = frozenset({"admin", "super_admin"})

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


def _asignar_ganador(combate: Combat, ganador_id: int) -> None:
    """Reescribe ``result`` de cada participante para reflejar el ganador.

    El resultado confirmado/editado es el que manda: el aggregate queda
    coherente antes de cualquier recálculo Elo.
    """
    for participante in combate.participants:
        participante.result = (
            ResultadoParticipante.VICTORIA
            if participante.user_id == ganador_id
            else ResultadoParticipante.DERROTA
        )


def _cerrar_confirmado(combate: Combat, ganador_id: int) -> None:
    """Cierra el combate en ``CONFIRMADO`` alineando el resultado declarado.

    El recálculo Elo on-write se lanza en :func:`confirm_combat` justo antes
    del commit, para que el cambio de estado y los índices viajen en la misma
    transacción (RNF008).
    """
    _asignar_ganador(combate, ganador_id)
    combate.status = transicionar(combate.status, EstadoCombate.CONFIRMADO)


def _procesar_elo(combat_id: int) -> None:
    """HOOK (Sprint 6): recálculo on-write del combate en la misma sesión.

    Se lanza justo antes del commit de :func:`confirm_combat` para que el
    cierre del combate y los índices viajen en la misma transacción (RNF008).

    La importación es diferida para evitar un ciclo de imports
    (``ranking.services`` lee los modelos de combate).
    """
    from app.modules.ranking.services import process_confirmed_combat

    process_confirmed_combat(combat_id, commit=False)


def _invalidar_caché_ranking() -> None:
    """Invalida la caché del ranking público tras cambiar índices (RNF004).

    Import diferido para no crear un ciclo con ``public_api`` (que importa los
    repositorios de ranking).
    """
    from app.modules.public_api.services import invalidar_cache

    invalidar_cache()


def _recalcular_comunidad(community_id: int) -> None:
    """HOOK (Sprint 6): recálculo COMPLETO de la comunidad en la misma sesión.

    La edición admin puede cambiar un resultado **ya procesado**, así que no
    basta con reprocesar ese combate (se duplicarían deltas): se reconstruyen
    todos los índices replayando el historial.
    """
    from app.modules.ranking.services import recalculate_full

    recalculate_full(community_id, commit=False)


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

    try:
        if combate.status is EstadoCombate.CONFIRMADO:
            # RNF008: índice actualizado en la misma transacción que el cierre.
            _procesar_elo(combate.id)
        CombatRepository.save()
    except Exception:
        CombatRepository.rollback()
        raise
    _invalidar_caché_ranking()
    return combate


def _texto(valor) -> str | None:
    """Serializa un valor para guardarlo como traza de auditoría."""
    return None if valor is None else str(valor)


def _normalizar_edicion(campo: str, valor, combate: Combat) -> tuple[str, object]:
    """Valida un campo editable y devuelve su nombre canónico y valor normalizado.

    Raises:
        DomainError: campo no editable o valor inválido para ese campo.
    """
    if campo in ("winner", "winner_id"):
        if valor is None or valor == "":
            raise DomainError("El campo 'winner_id' es obligatorio.")
        try:
            ganador_id = int(valor)
        except (TypeError, ValueError) as exc:
            raise DomainError("'winner_id' debe ser un identificador numérico.") from exc
        if ganador_id not in combate.participante_ids:
            raise DomainError(
                "'winner_id' debe ser uno de los participantes del combate "
                f"({', '.join(str(i) for i in combate.participante_ids)})."
            )
        return "winner_id", ganador_id

    if campo == "played_at":
        return "played_at", _normalizar_fecha(valor)

    if campo == "referee_id":
        if valor is None or valor == "":
            return "referee_id", None
        arbitro = _usuario_o_error(valor, "referee_id")
        if arbitro.community_id != combate.community_id:
            raise DomainError(
                f"El árbitro debe pertenecer a la comunidad {combate.community_id}."
            )
        if arbitro.role.name not in ROLES_ARBITRO:
            raise DomainError(f"El usuario {arbitro.id} no tiene rol de árbitro.")
        return "referee_id", arbitro.id

    raise DomainError(
        f"El campo '{campo}' no es editable. Campos editables: "
        "winner_id, played_at, referee_id."
    )


def admin_edit_result(admin_id, combat_id, nuevos_datos) -> Combat:
    """Edición manual de un combate por un administrador (RF9 / RNF008).

    Reglas de dominio:

    - Permitido en **cualquier** estado, incluso ya ``RESUELTO``.
    - Solo ``admin``/``super_admin`` (403 para el resto).
    - Cada campo modificado deja una entrada en ``AuditLog`` con el valor
      anterior y el nuevo; también se audita el cambio de estado.
    - Al terminar el combate queda en ``RESUELTO``.

    Args:
        admin_id: administrador que ejecuta la edición.
        combat_id: combate a editar.
        nuevos_datos: campos a cambiar — ``winner_id`` (o ``winner``),
            ``played_at`` y/o ``referee_id`` (``None`` lo desasigna).

    Returns:
        El combate editado y en estado ``RESUELTO``.

    Raises:
        NotFoundError: combate o usuario inexistente (404).
        ForbiddenError: quien edita no es administrador o pertenece a otra
            comunidad (403).
        DomainError: objeto inválido, campo no editable, valor inválido o
            combate ya ``RESUELTO`` sin cambios que aplicar (400).
    """
    combate = CombatRepository.get_by_id(combat_id)
    if combate is None:
        raise NotFoundError(f"No existe el combate {combat_id}.")

    admin = _usuario_o_error(admin_id, "admin_id")
    if admin.role.name not in ROLES_ADMIN:
        raise ForbiddenError("Solo un administrador puede editar el resultado de un combate.")
    if admin.community_id != combate.community_id:
        # RNF006: aislamiento de datos entre comunidades.
        raise ForbiddenError("No tienes permisos para editar combates de otra comunidad.")

    if not isinstance(nuevos_datos, Mapping):
        raise DomainError("'nuevos_datos' debe ser un objeto con los campos a editar.")

    valores: dict[str, object] = {}
    for campo, valor in nuevos_datos.items():
        nombre, normalizado = _normalizar_edicion(campo, valor, combate)
        if nombre in valores:
            raise DomainError(f"El campo '{nombre}' aparece más de una vez.")
        valores[nombre] = normalizado

    actuales = {
        "winner_id": combate.ganador_id,
        "played_at": combate.played_at,
        "referee_id": combate.referee_id,
    }
    cambios = {c: (actuales[c], v) for c, v in valores.items() if actuales[c] != v}

    if not cambios and combate.status is EstadoCombate.RESUELTO:
        raise DomainError(f"El combate {combate.id} no tiene cambios que aplicar.")

    for campo, (anterior, nuevo) in cambios.items():
        if campo == "winner_id":
            _asignar_ganador(combate, nuevo)
        else:
            setattr(combate, campo, nuevo)
        AuditLogRepository.add(
            AuditLog(
                combat_id=combate.id,
                admin_id=admin.id,
                campo=campo,
                valor_anterior=_texto(anterior),
                valor_nuevo=_texto(nuevo),
                community_id=combate.community_id,
            )
        )

    if combate.status is not EstadoCombate.RESUELTO:
        estado_anterior = combate.status
        combate.status = transicionar(combate.status, EstadoCombate.RESUELTO)
        AuditLogRepository.add(
            AuditLog(
                combat_id=combate.id,
                admin_id=admin.id,
                campo="status",
                valor_anterior=estado_anterior.value,
                valor_nuevo=EstadoCombate.RESUELTO.value,
                community_id=combate.community_id,
            )
        )

    try:
        # RNF008: la edición admin puede cambiar resultados ya procesados.
        _recalcular_comunidad(combate.community_id)
        CombatRepository.save()
    except Exception:
        CombatRepository.rollback()
        raise
    _invalidar_caché_ranking()
    return combate

