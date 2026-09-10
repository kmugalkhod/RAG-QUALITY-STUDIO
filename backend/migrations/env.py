from app.models.pipeline import Pipeline, PipelineVersion  # noqa: F401
from app.models.query import QueryRun  # noqa: F401
from alembic import context
from app.models.index import IndexVersion, IndexChunk  # noqa: F401
from app.db.session import Base, engine
from app.models.document import Document, ProcessingRun, Chunk  # noqa: F401
from app.models.project import Project  # noqa: F401

if context.is_offline_mode():
    from app.core.config import settings

    context.configure(
        url=settings.database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
