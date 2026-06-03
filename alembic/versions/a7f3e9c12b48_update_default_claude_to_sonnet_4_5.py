#
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""update_default_claude_to_sonnet_4_5

The seeded default Anthropic model (Claude 3.7 Sonnet,
anthropic.claude-3-7-sonnet-20250219-v1:0) no longer has an inference profile
available in the deployment region, so every knowledge-base / chatbot call
failed with ResourceNotFoundException. Point the default at Claude Sonnet 4.5,
which is available as an inference profile (eu.anthropic.claude-sonnet-4-5-...).

Revision ID: a7f3e9c12b48
Revises: 6c9fc5098093
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7f3e9c12b48'
down_revision: Union[str, None] = '6c9fc5098093'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Repoint the default Anthropic model from the now-unavailable Claude 3.7
    # Sonnet to Claude Sonnet 4.5 (keeps inference profile + KB support).
    op.execute("""
        UPDATE public.ai_models
        SET
            "name" = 'Claude Sonnet 4.5',
            provider = 'Anthropic',
            identifier = 'anthropic.claude-sonnet-4-5-20250929-v1:0',
            is_default = true,
            max_input_tokens = 200000,
            max_output_tokens = 8000,
            input_modalities = '["Text", "Image"]'::jsonb,
            output_modalities = '["Text"]'::jsonb,
            inference = true,
            supports_knowledge_base = true,
            category = 'high-end',
            description = 'Best for document evaluation, complex reasoning, and high-accuracy tasks'
        WHERE identifier = 'anthropic.claude-3-7-sonnet-20250219-v1:0';
    """)


def downgrade() -> None:
    # Revert the default Anthropic model back to Claude 3.7 Sonnet.
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
            description = 'Budget-friendly models for general chat and lightweight tasks'
        WHERE identifier = 'anthropic.claude-sonnet-4-5-20250929-v1:0';
    """)
