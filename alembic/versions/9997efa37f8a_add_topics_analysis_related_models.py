# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""Add topics analysis related models

Revision ID: 9997efa37f8a
Revises: 3c97fcbec3ae
Create Date: 2025-07-02 10:22:53.510590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9997efa37f8a'
down_revision: Union[str, None] = '3c97fcbec3ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('etl_tasks_configuration',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.Enum('topics_analysis', name='etltasktype'), nullable=False),
        sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_etl_tasks_configuration_id'), 'etl_tasks_configuration', ['id'], unique=False)

    op.create_table('etl_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.Enum('topics_analysis', name='etltasktype'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='etltaskstatus'), nullable=False),
        sa.Column('result', sa.Enum('success', 'error', name='etltaskresult'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_etl_tasks_id'), 'etl_tasks', ['id'], unique=False)

    op.create_table('conversation_topics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chatbot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('topics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('global_topic', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['chatbot_id'], ['chatbots.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversation_topics_id'), 'conversation_topics', ['id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_conversation_topics_id'), table_name='conversation_topics')
    op.drop_table('conversation_topics')
    op.drop_index(op.f('ix_etl_tasks_id'), table_name='etl_tasks')
    op.drop_table('etl_tasks')
    op.drop_index(op.f('ix_etl_tasks_configuration_id'), table_name='etl_tasks_configuration')
    op.drop_table('etl_tasks_configuration')

    # Clean enums / types
    op.execute(sa.text('DROP TYPE IF EXISTS etltasktype'))
    op.execute(sa.text('DROP TYPE IF EXISTS etltaskstatus'))
    op.execute(sa.text('DROP TYPE IF EXISTS etltaskresult'))
