"""Tests de las vistas HTML base del Sprint 7.2 (layout, login y registro)."""

from app.extensions import db
from app.modules.iam import services
from app.modules.iam.repositories import RoleRepository

VALIDO = {"email": "ana@x.com", "password": "password123", "name": "Ana Rojas"}


def _crear_admin(email="dona@x.com"):
    admin = services.register_user(email=email, password="password123", name="Dona Eva")
    admin.role_id = RoleRepository.get_by_name("admin").id
    db.session.commit()
    return admin


def test_portada_publica(client, roles):
    """GET / pinta la portada sin exigir sesión."""
    r = client.get("/")
    assert r.status_code == 200
    assert "Ranking Elo" in r.get_data(as_text=True)
    assert "Crear cuenta" in r.get_data(as_text=True)


def test_pagina_login(client, roles):
    r = client.get("/login")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert 'method="post"' in texto
    assert 'name="email"' in texto
    assert 'name="password"' in texto


def test_pagina_registro(client, roles):
    r = client.get("/registro")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert 'name="name"' in texto
    assert "mínimo 8 caracteres" in texto


def test_login_por_formulario_abre_sesion(client, roles):
    """El formulario del navegador usa el mismo servicio que la API."""
    services.register_user(**VALIDO)

    r = client.post("/login", data={"email": VALIDO["email"], "password": VALIDO["password"]})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/ranking")

    me = client.get("/me")
    assert me.status_code == 200
    assert me.get_json()["name"] == "Ana Rojas"


def test_login_formulario_credenciales_invalidas(client, roles):
    services.register_user(**VALIDO)

    r = client.post("/login", data={"email": VALIDO["email"], "password": "mala"})
    assert r.status_code == 401
    texto = r.get_data(as_text=True)
    assert "Credenciales inválidas." in texto
    # El correo del intento se conserva para no hacerlo repetir la escritura.
    assert VALIDO["email"] in texto
    assert client.get("/me").status_code == 401


def test_registro_por_formulario_crea_cuenta_y_sesion(client, roles):
    r = client.post("/registro", data=VALIDO)
    assert r.status_code == 302

    me = client.get("/me").get_json()
    assert me["name"] == "Ana Rojas"
    assert me["role"] == "jugador"


def test_registro_email_duplicado(client, roles):
    services.register_user(**VALIDO)

    r = client.post("/registro", data=VALIDO)
    assert r.status_code == 409
    assert "Ya existe una cuenta" in r.get_data(as_text=True)


def test_registro_contraseña_corta(client, roles):
    r = client.post(
        "/registro", data={**VALIDO, "password": "corta"}
    )
    assert r.status_code == 400
    assert "al menos 8 caracteres" in r.get_data(as_text=True)


def test_registro_nombre_vacio(client, roles):
    r = client.post("/registro", data={**VALIDO, "name": " "})
    assert r.status_code == 400
    assert "nombre" in r.get_data(as_text=True).lower()


def test_salir_cierra_sesion(client, roles):
    services.register_user(**VALIDO)
    client.post("/login", data={"email": VALIDO["email"], "password": VALIDO["password"]})
    assert client.get("/me").status_code == 200

    r = client.get("/salir")
    assert r.status_code == 302
    assert client.get("/me").status_code == 401


def test_salir_sin_sesion_redirige_al_login(client, roles):
    r = client.get("/salir")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
    assert "next=/salir" in r.headers["Location"]


def test_login_conserva_la_ruta_original(client, roles):
    """El parámetro next interno se respeta (flujo: → login → volver)."""
    services.register_user(**VALIDO)

    r = client.post(
        "/login?next=/me",
        data={"email": VALIDO["email"], "password": VALIDO["password"]},
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/me")


def test_login_ignora_destinos_externos(client, roles):
    """Abierto a open redirect: next externo o de protocolo-relativo se ignora."""
    services.register_user(**VALIDO)
    datos = {"email": VALIDO["email"], "password": VALIDO["password"]}

    for destino in ("https://evil.example", "//evil.example", "/\\evil"):
        r = client.post(f"/login?next={destino}", data=datos)
        assert r.status_code == 302
        assert "evil" not in r.headers["Location"]


def test_layout_muestra_solo_lo_que_corresponde(client, roles):
    """La navegación cambia según haya sesión (elemento clave del layout)."""
    services.register_user(**VALIDO)

    anonimo = client.get("/login").get_data(as_text=True)
    assert "Registrarse" in anonimo
    assert "Salir" not in anonimo

    client.post("/login", data={"email": VALIDO["email"], "password": VALIDO["password"]})
    con_sesion = client.get("/").get_data(as_text=True)
    assert "Ana Rojas" in con_sesion
    assert "Salir" in con_sesion
    assert "Registrarse" not in con_sesion


def test_rutas_api_siguen_devolviendo_json(client, roles):
    """Las vistas HTML no rompen la API JSON existente (Sprint 2)."""
    r = client.post("/auth/register", json=VALIDO)
    assert r.status_code == 201
    assert r.get_json()["role"] == "jugador"
    assert client.get("/me").get_json()["email"] == VALIDO["email"]
