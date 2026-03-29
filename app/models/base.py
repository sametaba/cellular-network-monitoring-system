from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    All models inherit from this class so Alembic and SQLAlchemy can
    discover them through `Base.metadata`.
    """
    pass
