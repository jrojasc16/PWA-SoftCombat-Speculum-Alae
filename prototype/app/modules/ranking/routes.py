"""Blueprint ranking: recálculo manual admin (RF9 / RNF008)."""

from flask import Blueprint, jsonify
from flask_login import current_user

from app.modules.ranking import services
from app.shared.decorators import api_login_required, role_required

bp = Blueprint("ranking", __name__)


@bp.post("/admin/ranking/recalculate")
@api_login_required
@role_required("admin", "super_admin")
def recalcular_ranking():
    """Reconstruye los índices de mi comunidad replayando sus combates.

    Es la vía manual del RNF008: borra y recalcula ``ratings`` y
    ``rating_history`` en una única transacción, en orden cronológico de juego.

    - ``200``: ``{"community_id": n, "combats_processed": n}``.
    - ``403``: rol insuficiente.
    """
    comunidad = current_user.community_id
    procesados = services.recalculate_full(comunidad)
    return (
        jsonify({"community_id": comunidad, "combats_processed": procesados}),
        200,
    )
