from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    isolation_level="REPEATABLE READ",
    pool_timeout=5,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000"},
)


def get_session():
    with Session(engine) as session:
        yield session


def get_deployment_session():
    """Admissions need a fresh committed view after their PostgreSQL lock."""
    with Session(engine.execution_options(isolation_level="READ COMMITTED")) as session:
        yield session
