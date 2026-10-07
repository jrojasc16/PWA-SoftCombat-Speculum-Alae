"""Auxiliares de adaptación HTTP compartidos por las rutas de todos los módulos.

Las rutas solo traducen HTTP ↔ servicios (regla transversal 4): aquí se
agrupa lo común a todos los blueprints (lectura del cuerpo de la petición).
"""

from flask import request


def payload_json_o_formulario() -> dict:
    """Cuerpo de la petición como dict, aceptando JSON o formulario web.

    Si la petición no trae cuerpo devuelve un dict vacío (los servicios son los
    que validan los campos obligatorios y devuelven el error de dominio).
    """
    cuerpo = request.get_json(silent=True)
    if isinstance(cuerpo, dict):
        return cuerpo
    return request.form.to_dict()
