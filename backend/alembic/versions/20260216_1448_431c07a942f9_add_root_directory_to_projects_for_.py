"""Add root_directory to projects for monorepo support

Revision ID: 431c07a942f9
Revises: a7f3d4e2b9c1
Create Date: 2026-02-16 14:48:16.141552+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '431c07a942f9'
down_revision: Union[str, None] = 'a7f3d4e2b9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add root_directory column to projects table
    op.add_column('projects', sa.Column('root_directory', sa.String(length=255), nullable=False, server_default=''))


def downgrade() -> None:
    # Remove root_directory column from projects table
    op.drop_column('projects', 'root_directory')
