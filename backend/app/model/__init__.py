# Import every model here so Base.metadata knows all tables (Alembic autogenerate relies on it).
from app.model.base import Base
from app.model.paste import Paste

__all__ = ["Base", "Paste"]
