"""Add active_deployment_id to projects

Revision ID: e2b7c8d9f0a1
Revises: d1a6b7c8e9f0
Create Date: 2026-02-19 01:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b7c8d9f0a1'
down_revision: Union[str, None] = 'd1a6b7c8e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('active_deployment_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_projects_active_deployment_id'), 'projects', ['active_deployment_id'], unique=False)
    op.create_foreign_key('fk_projects_active_deployment_id', 'projects', 'deployments', ['active_deployment_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_projects_active_deployment_id', 'projects', type_='foreignkey')
    op.drop_index(op.f('ix_projects_active_deployment_id'), table_name='projects')
    op.drop_column('projects', 'active_deployment_id')
