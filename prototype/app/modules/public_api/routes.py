"""Endpoint público GET /api/ranking (sin auth, preparado para API key)."""

from flask import Blueprint

bp = Blueprint("public_api", __name__)
