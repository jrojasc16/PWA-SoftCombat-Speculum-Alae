"""Auxiliares de adaptación HTTP compartidos por las rutas de todos los módulos.

Las rutas solo traducen HTTP ↔ servicios (regla transversal 4): aquí se
agrupa lo común a todos los blueprints (lectura del cuerpo de la petición).
"""

from flask import request

# Límites de paginación compartidos por todos los endpoints con página
# (respuesta acotada siempre; RNF004).
PAGINA_POR_DEFECTO = 50
PAGINA_MAXIMO = 100


def payload_json_o_formulario() -> dict:
    """Cuerpo de la petición como dict, aceptando JSON o formulario web.

    Si la petición no trae cuerpo devuelve un dict vacío (los servicios son los
    que validan los campos obligatorios y devuelven el error de dominio).
    """
    cuerpo = request.get_json(silent=True)
    if isinstance(cuerpo, dict):
        return cuerpo
    return request.form.to_dict()


def param_entero(
    nombre: str, valor, defecto: int, minimo: int, maximo: int | None = None
) -> int:
    """Convierte y valida un parámetro de consulta entero.

    Args:
        nombre: nombre del parámetro (para el mensaje de error).
        valor: valor crudo de ``request.args`` (``None`` → usa ``defecto``).
        defecto: valor cuando el parámetro no viene.
        minimo: cota inferior incluida.
        maximo: cota superior incluida (``None`` sin cota).

    Returns:
        El entero validado.

    Raises:
        DomainError: valor no numérico o fuera de rango (400).
    """
    from app.shared.errors import DomainError  # import diferido: evita ciclos

    if valor is None:
        return defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise DomainError(f"El parámetro '{nombre}' debe ser un entero.") from exc
    if numero < minimo or (maximo is not None and numero > maximo):
        rango = f"entre {minimo} y {maximo}" if maximo else f">= {minimo}"
        raise DomainError(f"El parámetro '{nombre}' debe ser {rango}.")
    return numero

