"""Blueprint combat: reporte, confirmación y edición admin de combates.

Las entradas de los métodos post y get son JSON (enviados por el body de la
petición) o formulario web (enviado por el navegador); las salidas son JSON.

Las rutas solo adaptan HTTP ↔ servicios (regla transversal 4). El emisor del
reporte **siempre** es el usuario autenticado (nunca se confía en un id que
envíe el cliente). Las confirmaciones (``POST /combats/<id>/confirm``) y la
edición admin (``PATCH /admin/combats/<id>``) llegan en el Sprint 5.
"""

from flask import Blueprint, jsonify
from flask_login import current_user

from app.modules.combat import services
from app.modules.combat.repositories import CombatRepository
from app.shared.decorators import api_login_required
from app.shared.errors import NotFoundError
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
    """
    data = payload_json_o_formulario()
    combate = services.report_combat(
        reporter_id=current_user.id,
        participants=data.get("participants"),
        winner=data.get("winner"),
        played_at=data.get("played_at"),
        referee_id=data.get("referee_id"),
    )
    return jsonify(_combat_json(combate)), 201


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
