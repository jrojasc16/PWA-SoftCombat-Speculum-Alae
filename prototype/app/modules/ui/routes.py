"""Vistas HTML del prototipo (Sprint 7.2): layout, login y registro.

Reglas de la capa de presentación (regla transversal 4):

- No toca SQLAlchemy: solo llama a ``iam.services``.
- Consume el **mismo** contrato JSON que la API: la autenticación del
  formulario usa ``authenticate``/``register_user`` y cierra con
  ``login_user`` de Flask-Login (sesión por cookie, no JWT).
- ``next`` solo acepta rutas relativas internas (nunca un sitio externo).
"""

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.modules.iam import services as iam_services
from app.shared.decorators import login_redirect
from app.shared.errors import DomainError

bp = Blueprint("ui", __name__)

# Destino por defecto tras autenticarse: la portada pública.
# En la tarea 7.3 pasa a ser la vista de ranking (``ui.ranking``).
DESPUES_DE_ENTRAR = "ui.inicio"


def _destino_seguro(destino) -> str:
    """Ruta interna segura a la que volver tras el login.

    Solo se aceptan rutas relativas (``/historial``): esto cierra el hueco
    de open redirect (``https://otro-sitio``, ``//otro-sitio`` o con ``\\``).
    """
    if (
        isinstance(destino, str)
        and destino.startswith("/")
        and not destino.startswith("//")
        and "\\" not in destino
        and "://" not in destino
    ):
        return destino
    return url_for(DESPUES_DE_ENTRAR)


@bp.app_context_processor
def inyectar_usuario():
    """Expone ``usuario`` (Flask-Login) a todos los templates del layout."""
    return {"usuario": current_user}


@bp.get("/")
def inicio():
    """Portada pública del prototipo (punto de entrada de la PWA)."""
    return render_template("inicio.html")


@bp.route("/login", methods=["GET", "POST"])
def login_view():
    """Página de inicio de sesión (RF1): formulario HTML sobre la API IAM.

    GET muestra el formulario; POST autentica y redirige a ``next`` (o al
    ranking). Ante un error de dominio se vuelve a pintar la página con el
    mensaje y el código correspondiente (401 para credenciales inválidas).
    """
    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next"))

    email = request.form.get("email", "")
    # El `next` puede venir en la query (acción del formulario) o en el cuerpo.
    destino = _destino_seguro(request.args.get("next") or request.form.get("next"))
    try:
        user = iam_services.authenticate(
            email=email, password=request.form.get("password", "")
        )
    except DomainError as exc:
        return (
            render_template(
                "login.html",
                error=exc.message,
                valores={"email": email},
                next=destino,
            ),
            exc.status_code,
        )
    login_user(user)
    return redirect(destino)


@bp.route("/registro", methods=["GET", "POST"])
def registro_view():
    """Página de registro (RF1): crea la cuenta con rol ``jugador`` y entra.

    El registro es el paso 1 del flujo del jugador (RNF003): en un solo
    envío se crea la cuenta y queda la sesión iniciada.
    """
    if request.method == "GET":
        return render_template("registro.html")

    email = request.form.get("email", "")
    nombre = request.form.get("name", "")
    valores = {"email": email, "name": nombre}
    try:
        user = iam_services.register_user(
            email=email, password=request.form.get("password", ""), name=nombre
        )
    except DomainError as exc:
        return (
            render_template("registro.html", error=exc.message, valores=valores),
            exc.status_code,
        )
    login_user(user)
    return redirect(url_for(DESPUES_DE_ENTRAR))


@bp.get("/salir")
@login_redirect
def salir():
    """Cierra la sesión y vuelve al ranking (enlace de la navegación)."""
    logout_user()
    return redirect(url_for(DESPUES_DE_ENTRAR))
