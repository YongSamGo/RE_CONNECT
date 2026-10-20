"""DB URL은 환경 설정에서만 읽고 URL·SQL·파라미터를 로그에 출력하지 않는다."""

from alembic import context
from sqlalchemy import pool

from app.core.config import get_settings
from app.persistence import Base
from app.persistence.connection import build_engine, database_url

config = context.config
target_metadata = Base.metadata


def run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=database_url(get_settings()), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run_migrations(config.attributes["connection"])
else:
    engine = build_engine(get_settings(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
