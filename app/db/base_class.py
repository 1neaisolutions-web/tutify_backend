"""
SQLAlchemy base class for all models (no side-effect imports).

This module must stay import-safe: it should never import model modules,
so that models can import `Base` without creating circular imports.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

