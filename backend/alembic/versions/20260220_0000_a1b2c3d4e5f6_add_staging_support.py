"""Add staging environment support

Revision ID: a1b2c3d4e5f6
Revises: f3c8d9e0a1b2
Create Date: 2026-02-20 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f3c8d9e0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- environment_variables: add environment column ---
    op.add_column(
        'environment_variables',
        sa.Column('environment', sa.String(20), nullable=False, server_default='production'),
    )
    # Drop old unique constraint and create new one including environment
    op.drop_constraint('uq_env_var_project_key', 'environment_variables', type_='unique')
    op.create_unique_constraint(
        'uq_env_var_project_key_env',
        'environment_variables',
        ['project_id', 'key', 'environment'],
    )

    # --- projects: add staging columns ---
    op.add_column(
        'projects',
        sa.Column('staging_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column(
        'projects',
        sa.Column('staging_deployment_id', sa.Integer(), sa.ForeignKey('deployments.id'), nullable=True),
    )
    op.add_column(
        'projects',
        sa.Column('staging_fc_function_name', sa.String(255), nullable=True),
    )
    op.add_column(
        'projects',
        sa.Column('staging_fc_endpoint_url', sa.String(512), nullable=True),
    )
    op.add_column(
        'projects',
        sa.Column('staging_domain', sa.String(255), nullable=True),
    )
    op.add_column(
        'projects',
        sa.Column('staging_password', sa.String(255), nullable=True),
    )
    op.create_index('ix_projects_staging_deployment_id', 'projects', ['staging_deployment_id'])

    # --- deployments: add is_staging column ---
    op.add_column(
        'deployments',
        sa.Column('is_staging', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    # --- deployments ---
    op.drop_column('deployments', 'is_staging')

    # --- projects ---
    op.drop_index('ix_projects_staging_deployment_id', table_name='projects')
    op.drop_column('projects', 'staging_password')
    op.drop_column('projects', 'staging_domain')
    op.drop_column('projects', 'staging_fc_endpoint_url')
    op.drop_column('projects', 'staging_fc_function_name')
    op.drop_column('projects', 'staging_deployment_id')
    op.drop_column('projects', 'staging_enabled')

    # --- environment_variables ---
    op.drop_constraint('uq_env_var_project_key_env', 'environment_variables', type_='unique')
    op.create_unique_constraint(
        'uq_env_var_project_key',
        'environment_variables',
        ['project_id', 'key'],
    )
    op.drop_column('environment_variables', 'environment')
