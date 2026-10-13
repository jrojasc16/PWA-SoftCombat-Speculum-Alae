"""Blueprint history: historial de partidas por usuario (RF10).

Solo se expone la consulta del propio historial: nunca la de otro usuario.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.modules.history import services
from app.shared.decorators import api_login_required
from app.shared.http import PAGINA_MAXIMO, PAGINA_POR_DEFECTO, param_entero

bp = Blueprint("history", __name__)


@bp.get("/me/history")
@api_login_required
def mi_historial():
    """Mis combates con resultado y variación de índice (401 sin sesión).

    Query string: ``page`` (por defecto 1) y ``per_page`` (por defecto 50,
    máximo 100). El orden es del más reciente al más antiguo.
    """
    page = param_entero("page", request.args.get("page"), 1, 1)
    per_page = param_entero(
        "per_page", request.args.get("per_page"), PAGINA_POR_DEFECTO, 1, PAGINA_MAXIMO
    )
    payload = services.historial_de_usuario(
        current_user.id, current_user.community_id, page, per_page
    )
    return jsonify(payload), 200
