"""initial schema

Revision ID: 4f70511b1a31
Revises:
Create Date: 2026-05-07 15:44:19.751181

"""
from typing import Sequence, Union

from alembic import op

from app.database import Base
import app.db_models  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "4f70511b1a31"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the current SQLAlchemy metadata."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Drop the current SQLAlchemy metadata."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
