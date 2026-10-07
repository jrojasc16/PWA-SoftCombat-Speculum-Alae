"""Blueprint combat: reporte, confirmación y edición admin de combates.

Las entradas de los métodos post y get son JSON (enviados por el body de la
petición) o formulario web (enviado por el navegador); las salidas son JSON.

Las rutas solo adaptan HTTP ↔ servicios (regla transversal 4). El emisor del
reporte y de la confirmación **siempre** es el usuario autenticado (nunca se
confía en un id que envíe el cliente). Las rutas de administración exigen rol
``admin``/``super_admin`` (RBAC de roles fijos del MVP).
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.modules.combat import services
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.combat.repositories import CombatRepository
from app.shared.decorators import api_login_required, role_required
from app.shared.errors import DomainError, NotFoundError
from app.shared.http import payload_json_o_formulario

bp = Blueprint("combat", __name__)


def _combat_json(combat) -> dict:
    """Proyección JSON de un combate (sin datos sensibles de los usuarios)."""
    return {
        "id": combat.id,
        "community_id": combat.community_id,
        "status": combat.status.value,
        "reporter_id": combat.reporter_id,
        "referee_id": combat.referee_id,
        "played_at": combat.played_at.isoformat(),
        "processed": combat.processed,
        "created_at": combat.created_at.isoformat(),
        "participants": [
            {"user_id": p.user_id, "name": p.user.name, "result": p.result.value}
            for p in combat.participants
        ],
    }


@bp.post("/combats")
@api_login_required
def crear_combate():
    """Reporta un combate nuevo (queda ``PENDIENTE``).

    - ``201``: combate creado en estado ``PENDIENTE``.
    - ``200``: ``client_request_id`` ya existía → se devuelve el combate
      original sin crear otro (idempotencia de los reenvíos offline, RF5).
    """
    data = payload_json_o_formulario()
    combate, creado = services.report_combat(
        reporter_id=current_user.id,
        participants=data.get("participants"),
        winner=data.get("winner"),
        played_at=data.get("played_at"),
        referee_id=data.get("referee_id"),
        client_request_id=data.get("client_request_id"),
    )
    return jsonify(_combat_json(combate)), 201 if creado else 200


@bp.get("/combats/pending")
@api_login_required
def combates_pendientes():
    """Combates ``PENDIENTE`` que me tocan confirmar (soy participante o árbitro)."""
    pendientes = CombatRepository.pendientes_de_usuario(
        current_user.id, current_user.community_id
    )
    return jsonify([_combat_json(c) for c in pendientes]), 200


@bp.get("/combats/<int:combat_id>")
@api_login_required
def detalle_combate(combat_id: int):
    """Detalle de un combate (404 si no existe)."""
    combate = CombatRepository.get_by_id(combat_id)
    if combate is None:
        raise NotFoundError(f"No existe el combate {combat_id}.")
    return jsonify(_combat_json(combate)), 200


@bp.post("/combats/<int:combat_id>/confirm")
@api_login_required
def confirmar_combate(combat_id: int):
    """Registra la confirmación del usuario autenticado (RF8).

    El cuerpo trae ``winner_id`` (JSON o campo de formulario): el id del
    participante que este usuario declara ganador.

    - ``200``: confirmación registrada (``PENDIENTE``, ``CONFIRMADO`` o
      ``CONFLICTO`` según lo que lleven los demás).
    - ``409``: este usuario ya había confirmado.
    """
    data = payload_json_o_formulario()
    combate = services.confirm_combat(
        user_id=current_user.id,
        combat_id=combat_id,
        result={"winner_id": data.get("winner_id", data.get("winner"))},
    )
    return jsonify(_combat_json(combate)), 200


@bp.route("/admin/combats/<int:combat_id>", methods=["PATCH", "POST"])
@api_login_required
@role_required("admin", "super_admin")
def editar_combate_admin(combat_id: int):
    """Edición manual de un combate con registro en ``AuditLog`` (RF9).

    Acepta ``PATCH`` (API/PWA) y ``POST`` (formulario web, que no puede enviar
    PATCH por sí mismo). Campos editables: ``winner_id``, ``played_at`` y
    ``referee_id``; cualquier otro campo responde ``400``. Los campos que
    empiezan con ``_`` (metadatos del formulario, p. ej. ``_method``) se ignoran.
    """
    data = {
        campo: valor
        for campo, valor in payload_json_o_formulario().items()
        if not campo.startswith("_")
    }
    combate = services.admin_edit_result(current_user.id, combat_id, data)
    return jsonify(_combat_json(combate)), 200


@bp.get("/admin/combats")
@api_login_required
@role_required("admin", "super_admin")
def listar_combates_admin():
    """Combates de mi comunidad para el panel admin (``?status=CONFLICTO``)."""
    estado = request.args.get("status")
    if estado:
        try:
            estado = EstadoCombate(estado)
        except ValueError as exc:
            raise DomainError(
                f"Estado inválido '{estado}': use PENDIENTE, CONFIRMADO, "
                "CONFLICTO o RESUELTO."
            ) from exc
    combates = CombatRepository.listar_admin(current_user.community_id, estado)
    return jsonify([_combat_json(c) for c in combates]), 200

