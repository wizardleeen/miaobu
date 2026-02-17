"""Add Python deployment support

Revision ID: b8e4f5a1c2d3
Revises: 431c07a942f9
Create Date: 2026-02-17 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e4f5a1c2d3'
down_revision: Union[str, None] = '431c07a942f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add project_type to projects
    op.add_column('projects', sa.Column('project_type', sa.String(10), nullable=False, server_default='static'))

    # Add Python-specific columns to projects
    op.add_column('projects', sa.Column('python_version', sa.String(20), nullable=True))
    op.add_column('projects', sa.Column('start_command', sa.String(512), nullable=True))
    op.add_column('projects', sa.Column('python_framework', sa.String(50), nullable=True))
    op.add_column('projects', sa.Column('fc_function_name', sa.String(255), nullable=True))
    op.add_column('projects', sa.Column('fc_endpoint_url', sa.String(512), nullable=True))

    # Add DEPLOYING status to the PostgreSQL enum
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'DEPLOYING' AFTER 'UPLOADING'")

    # Add FC columns to deployments
    op.add_column('deployments', sa.Column('fc_function_version', sa.String(255), nullable=True))
    op.add_column('deployments', sa.Column('fc_image_uri', sa.String(512), nullable=True))

    # Create environment_variables table
    op.create_table(
        'environment_variables',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('is_secret', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'key', name='uq_env_var_project_key'),
    )
    op.create_index(op.f('ix_environment_variables_id'), 'environment_variables', ['id'])
    op.create_index(op.f('ix_environment_variables_project_id'), 'environment_variables', ['project_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_environment_variables_project_id'), table_name='environment_variables')
    op.drop_index(op.f('ix_environment_variables_id'), table_name='environment_variables')
    op.drop_table('environment_variables')

    op.drop_column('deployments', 'fc_image_uri')
    op.drop_column('deployments', 'fc_function_version')

    op.drop_column('projects', 'fc_endpoint_url')
    op.drop_column('projects', 'fc_function_name')
    op.drop_column('projects', 'python_framework')
    op.drop_column('projects', 'start_command')
    op.drop_column('projects', 'python_version')
    op.drop_column('projects', 'project_type')
