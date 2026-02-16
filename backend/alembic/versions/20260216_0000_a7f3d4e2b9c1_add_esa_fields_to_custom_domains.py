"""Add ESA fields to custom_domains

Revision ID: a7f3d4e2b9c1
Revises: 76cb3e62840f
Create Date: 2026-02-16 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f3d4e2b9c1'
down_revision: Union[str, None] = '76cb3e62840f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ESA fields to custom_domains table
    op.add_column('custom_domains', sa.Column('esa_saas_id', sa.String(length=255), nullable=True))
    op.add_column('custom_domains', sa.Column('esa_status', sa.String(length=50), nullable=True))
    op.add_column('custom_domains', sa.Column('cname_target', sa.String(length=255), nullable=True, server_default='cname.metavm.tech'))
    op.add_column('custom_domains', sa.Column('active_deployment_id', sa.Integer(), nullable=True))
    op.add_column('custom_domains', sa.Column('edge_kv_synced', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('custom_domains', sa.Column('edge_kv_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('custom_domains', sa.Column('auto_update_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('custom_domains', sa.Column('domain_type', sa.String(length=20), nullable=False, server_default='esa'))

    # Create foreign key for active_deployment_id
    op.create_foreign_key(
        'fk_custom_domains_active_deployment',
        'custom_domains',
        'deployments',
        ['active_deployment_id'],
        ['id']
    )

    # Create indexes
    op.create_index(op.f('ix_custom_domains_esa_saas_id'), 'custom_domains', ['esa_saas_id'], unique=False)
    op.create_index(op.f('ix_custom_domains_active_deployment_id'), 'custom_domains', ['active_deployment_id'], unique=False)


def downgrade() -> None:
    # Remove indexes
    op.drop_index(op.f('ix_custom_domains_active_deployment_id'), table_name='custom_domains')
    op.drop_index(op.f('ix_custom_domains_esa_saas_id'), table_name='custom_domains')

    # Remove foreign key
    op.drop_constraint('fk_custom_domains_active_deployment', 'custom_domains', type_='foreignkey')

    # Remove columns
    op.drop_column('custom_domains', 'domain_type')
    op.drop_column('custom_domains', 'auto_update_enabled')
    op.drop_column('custom_domains', 'edge_kv_synced_at')
    op.drop_column('custom_domains', 'edge_kv_synced')
    op.drop_column('custom_domains', 'active_deployment_id')
    op.drop_column('custom_domains', 'cname_target')
    op.drop_column('custom_domains', 'esa_status')
    op.drop_column('custom_domains', 'esa_saas_id')
