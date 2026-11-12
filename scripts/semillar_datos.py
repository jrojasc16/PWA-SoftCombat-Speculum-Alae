#!/usr/bin/env python3
"""Semilla de datos del prototipo Speculum-Alae (Sprint 12.4).

Genera ``--usuarios`` cuentas (por defecto 100, RNF002) y ``--combates``
duelos **confirmados** por el camino de dominio real (reporte → doble
confirmación → recálculo Elo on-write), de modo que ``GET /api/ranking``
sirva un ranking poblado para la prueba de carga (tarea 12.5).

Uso (desde la raíz del repo):

    venv/bin/python scripts/semillar_datos.py                       # 100 usuarios, 200 combates
    venv/bin/python scripts/semillar_datos.py --usuarios 100 --combates 300
    venv/bin/python scripts/semillar_datos.py --usuarios 100 --reset   # borra antes de crear

La BD es la de desarrollo (`instance/app.db`) salvo que se indique
``--database-url``. Los roles fijos deben existir (migración de seed).
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Permite ejecutar el script desde cualquier cwd (igual que run.py).
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "prototype"))

USUARIOS_POR_DEFECTO = 100
COMBATES_POR_DEFECTO = 200
# Contraseña única para la semilla: solo sirve para pruebas locales de carga.
PASSWORD_SEMILLA = "Semilla-Prueba-2026"
COMUNIDAD = 1


def _crear_app(database_url: str | None):
    """Crea la app en modo desarrollo (o con la URL indicada)."""
    if database_url:
        os.environ["DATABASE_URL"] = database_url
    from app import create_app

    return create_app("development")


def _asegurar_roles() -> None:
    """Comprueba que los 4 roles fijos existen (migración de datos)."""
    from app.extensions import db
    from app.modules.iam.models import Role

    existentes = {r.name for r in Role.query.all()}
    faltantes = {"jugador", "arbitro", "admin", "super_admin"} - existentes
    if faltantes:
        raise SystemExit(
            f"Faltan roles {sorted(faltantes)}. Ejecuta antes: "
            "(cd prototype && ../venv/bin/flask db upgrade)"
        )


def _borrar_todo() -> None:
    """Elimina índices, historial, combates y usuarios (orden seguro FK)."""
    from app.extensions import db
    from app.modules.combat.models import (
        AuditLog,
        Combat,
        Confirmation,
    )
    from app.modules.iam.models import User
    from app.modules.ranking.models import Rating, RatingHistory

    RatingHistory.query.delete()
    Rating.query.delete()
    AuditLog.query.delete()
    Confirmation.query.delete()
    # combats borra participants en cascada por la relación; si no, a mano:
    from app.modules.combat.models import CombatParticipant

    CombatParticipant.query.delete()
    Combat.query.delete()
    User.query.delete()
    db.session.commit()


def _crear_usuarios(n: int) -> list:
    """Crea ``n`` usuarios (roles variados) y devuelve la lista.

    Reparto: ~90 % jugador, ~5 % árbitro, ~4 % admin, ~1 % super_admin.
    """
    from app.extensions import bcrypt
    from app.modules.iam.models import User
    from app.modules.iam.repositories import RoleRepository, UserRepository

    roles = {
        nombre: RoleRepository.get_by_name(nombre)
        for nombre in ("jugador", "arbitro", "admin", "super_admin")
    }
    # Hash único por usuario; costo fija la config (12 en desarrollo).
    from flask import current_app

    rounds = current_app.config["BCRYPT_LOG_ROUNDS"]
    print(f"  Hasheando contraseñas con bcrypt costo {rounds}…")
    password_hash = bcrypt.generate_password_hash(PASSWORD_SEMILLA, rounds=rounds).decode()

    usuarios: list[User] = []
    for i in range(1, n + 1):
        if i == 1:
            rol = roles["super_admin"]
        elif i <= 5:
            rol = roles["admin"]
        elif i <= 10:
            rol = roles["arbitro"]
        else:
            rol = roles["jugador"]
        usuario = User(
            email=f"jugador{i:03d}@speculum-alae.test",
            password_hash=password_hash,
            name=f"Jugador {i:03d}",
            role_id=rol.id,
            community_id=COMUNIDAD,
            active=True,
        )
        UserRepository.add(usuario)
        usuarios.append(usuario)
    UserRepository.save()
    return usuarios


def _fecha_aleatoria(rng: random.Random) -> datetime:
    """Fecha de juego en los últimos 90 días (nunca futura)."""
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    offset = timedelta(minutes=rng.randint(0, 90 * 24 * 60))
    return ahora - offset


def _crear_combates_confirmados(usuarios: list, n_combates: int, rng: random.Random) -> int:
    """Reporta y confirma ``n_combates`` duelos vía los servicios de dominio.

    Cada combate: reporte por un participante + confirmación de ambos →
    ``CONFIRMADO`` con recálculo Elo en la misma transacción (RNF008).

    Primero garantiza que **cada** usuario juegue al menos un duelo (para que
    los ``n`` usuarios aparezcan en el ranking de la prueba de carga) y luego
    completa hasta ``n_combates`` con parejas aleatorias.

    Returns:
        Número de combates creados y cerrados.
    """
    from app.modules.combat.services import confirm_combat, report_combat

    ids = [u.id for u in usuarios]
    arbitros = [u.id for u in usuarios if u.role.name in ("arbitro", "admin", "super_admin")]
    creados = 0
    contador = 0  # índice estable para client_request_id

    def _jugar(a: int, b: int) -> bool:
        nonlocal creados, contador
        ganador = a if rng.random() < 0.5 else b
        reporter = a if rng.random() < 0.5 else b
        # ~30 % con árbitro asignado (distinto de los dos participantes:
        # si el árbitro fuera participante, su confirmación cerraría el
        # combate por prioridad y la segunda confirmación daría 409).
        candidatos = [u for u in arbitros if u not in (a, b)]
        referee = rng.choice(candidatos) if candidatos and rng.random() < 0.3 else None
        combate, nuevo = report_combat(
            reporter_id=reporter,
            participants=[a, b],
            winner=ganador,
            played_at=_fecha_aleatoria(rng),
            referee_id=referee,
            client_request_id=f"semilla-{contador:06d}",
        )
        contador += 1
        if not nuevo:
            return False
        # Ambos participantes declaran el mismo ganador → CONFIRMADO + Elo.
        # (El árbitro nunca confirma aquí: es distinto de a y b.)
        confirm_combat(a, combate.id, {"winner_id": ganador})
        confirm_combat(b, combate.id, {"winner_id": ganador})
        creados += 1
        return True

    # Fase 1: round-robin mínimo para que nadie quede fuera del ranking.
    barajado = ids[:]
    rng.shuffle(barajado)
    for i in range(0, len(barajado) - 1, 2):
        if creados >= n_combates:
            break
        _jugar(barajado[i], barajado[i + 1])
    # Si el número de usuarios es impar, el último juega contra el primero.
    if len(barajado) % 2 == 1 and creados < n_combates:
        _jugar(barajado[-1], barajado[0])

    # Fase 2: hasta n_combates con parejas aleatorias.
    ultimo_aviso = 0
    while creados < n_combates:
        a, b = rng.sample(ids, 2)
        _jugar(a, b)
        if creados - ultimo_aviso >= 50:
            ultimo_aviso = creados
            print(f"  … {creados}/{n_combates} combates")

    return creados


def _resumen() -> None:
    from app.modules.combat.domain.estados import EstadoCombate
    from app.modules.combat.models import Combat
    from app.modules.iam.models import User
    from app.modules.ranking.models import Rating

    usuarios = User.query.count()
    ratings = Rating.query.count()
    confirmados = Combat.query.filter_by(status=EstadoCombate.CONFIRMADO).count()
    pendientes = Combat.query.filter_by(status=EstadoCombate.PENDIENTE).count()
    print()
    print("=== Resumen de la semilla ===")
    print(f"  usuarios:          {usuarios}")
    print(f"  ratings activos:    {ratings}")
    print(f"  combates CONFIRMADO: {confirmados}")
    print(f"  combates PENDIENTE:  {pendientes}")
    if ratings:
        from app.modules.ranking.repositories import RatingRepository

        top = RatingRepository.listar(COMUNIDAD)[:5]
        print("  Top 5 ranking:")
        for pos, r in enumerate(top, 1):
            print(f"    {pos}. {r.user.name}: {r.points:.1f} ({r.matches_played} combates)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Semilla de datos para pruebas de carga.")
    parser.add_argument("--usuarios", type=int, default=USUARIOS_POR_DEFECTO)
    parser.add_argument("--combates", type=int, default=COMBATES_POR_DEFECTO)
    parser.add_argument("--reset", action="store_true", help="Borra usuarios/combates antes.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL SQLAlchemy alternativa (por defecto la de desarrollo).",
    )
    parser.add_argument("--seed", type=int, default=20261111, help="Semilla del RNG.")
    args = parser.parse_args()

    if args.usuarios < 2:
        print("--usuarios debe ser >= 2", file=sys.stderr)
        return 2

    app = _crear_app(args.database_url)
    rng = random.Random(args.seed)

    with app.app_context():
        from app.extensions import db

        db.create_all()  # no pisa tablas existentes; solo crea las que falten
        _asegurar_roles()
        if args.reset:
            print("Borrando datos existentes…")
            _borrar_todo()
        elif _hay_usuarios():
            print(
                "Ya hay usuarios en la BD: usa --reset para regenerar la semilla "
                "(los emails de la semilla son fijos y chocarían).",
                file=sys.stderr,
            )
            return 2

        print(f"Creando {args.usuarios} usuarios…")
        usuarios = _crear_usuarios(args.usuarios)
        print(f"Creando hasta {args.combates} combates confirmados…")
        creados = _crear_combates_confirmados(usuarios, args.combates, rng)
        print(f"Combates cerrados: {creados}")
        _resumen()

    return 0


def _hay_usuarios() -> bool:
    from app.modules.iam.models import User

    return User.query.count() > 0


if __name__ == "__main__":
    raise SystemExit(main())
