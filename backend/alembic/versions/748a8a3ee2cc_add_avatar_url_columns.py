"""add avatar url columns

Revision ID: 748a8a3ee2cc
Revises: 4f70511b1a31
Create Date: 2026-05-07 22:14:00.984981

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '748a8a3ee2cc'
down_revision: Union[str, Sequence[str], None] = '4f70511b1a31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('avatar_mime', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('avatar_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'avatar_updated_at')
    op.drop_column('users', 'avatar_mime')
    op.drop_column('users', 'avatar_url')
