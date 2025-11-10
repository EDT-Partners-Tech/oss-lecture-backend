# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""update_claude_3_7_sonnet_model

Revision ID: 5e01daebf9b3
Revises: d9be6249c441
Create Date: 2025-09-08 12:49:27.565869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5e01daebf9b3'
down_revision: Union[str, None] = 'd9be6249c441'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Actualizar el modelo Claude 3.7 Sonnet (ID=6)
    op.execute("""
        UPDATE public.ai_models
        SET 
            "name" = 'Claude 3.7 Sonnet',
            provider = 'Anthropic',
            identifier = 'anthropic.claude-3-7-sonnet-20250219-v1:0',
            is_default = true,
            max_input_tokens = 131000,
            max_output_tokens = 8000,
            input_modalities = '["Text", "Image"]'::jsonb,
            output_modalities = '["Text", "Image"]'::jsonb,
            inference = true,
            supports_knowledge_base = true,
            category = 'high-end',
            description = 'Budget-friendly models for general chat and lightweight tasks',
            region_id = 'bbbf5e14-e6b4-47ac-a9cd-026a49e91c10'::uuid,
            token_rate = 6.0,
            input_price = 0.003,
            output_price = 0.015
        WHERE identifier = 'anthropic.claude-3-5-sonnet-20240620-v1:0';
    """)


def downgrade() -> None:
    # Revertir los cambios del modelo Claude 3.7 Sonnet (ID=6) a Claude 3.5 Sonnet
    op.execute("""
        UPDATE public.ai_models
        SET 
            "name" = 'Claude 3.5 Sonnet',
            provider = 'Anthropic',
            identifier = 'anthropic.claude-3-5-sonnet-20240620-v1:0',
            is_default = true,
            max_input_tokens = 200000,
            max_output_tokens = 8000,
            input_modalities = '["Text", "Image"]'::jsonb,
            output_modalities = '["Text", "Image"]'::jsonb,
            inference = true,
            supports_knowledge_base = true,
            category = 'high-end',
            description = 'Budget-friendly models for general chat and lightweight tasks',
            region_id = 'bbbf5e14-e6b4-47ac-a9cd-026a49e91c10'::uuid,
            token_rate = 6.0,
            input_price = 0.003,
            output_price = 0.015
        WHERE identifier = 'anthropic.claude-3-7-sonnet-20250219-v1:0';
    """)
