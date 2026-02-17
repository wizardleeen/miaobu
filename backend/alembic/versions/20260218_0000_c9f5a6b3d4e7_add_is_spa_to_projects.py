"""Add is_spa to projects

Revision ID: c9f5a6b3d4e7
Revises: b8e4f5a1c2d3
Create Date: 2026-02-18 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f5a6b3d4e7'
down_revision: Union[str, None] = 'b8e4f5a1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('is_spa', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('projects', 'is_spa')
