"""Dipendenze comuni per i router FastAPI."""
from fastapi import Depends
from sqlalchemy.orm import Session

from ..core.database import get_db

DbSession = Depends(get_db)

__all__ = ["DbSession", "get_db", "Session"]
