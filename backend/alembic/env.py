from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app import config
from app.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

with create_engine(config.DATABASE_URL).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
