"""Activate specialist chatbots; seed chatbot_capability feature cost.

Revision ID: c1d2e3f4b5a6
Revises: 12a18f870c9f, b8c7d6e5f4a3, r4s5t6u7v8w9
Create Date: 2026-05-03

Merges three Alembic heads and re-enables all non-general chatbots for production.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c1d2e3f4b5a6"
down_revision: Union[str, tuple, None] = ("12a18f870c9f", "b8c7d6e5f4a3", "r4s5t6u7v8w9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SPECIALIST_SLUGS = (
    "literacy-lab-coach",
    "grammar-writing-mentor",
    "literature-analysis-expert",
    "advanced-knowledge-skills-coach",
    "unec-academic-development",
    "adaptive-math-strategist",
    "problem-solving-coach",
    "algebra-geometry-tutor",
    "stem-inquiry-mentor",
    "lab-safety-protocol-advisor",
    "environmental-science-guide",
    "business-studies-mentor",
    "career-readiness-coach",
    "marketing-branding-strategist",
    "visual-arts-studio-assistant",
    "music-performance-coach",
    "drama-theater-director",
    "coding-programming-tutor",
    "digital-literacy-advisor",
    "ai-machine-learning-educator",
)


def upgrade() -> None:
    in_list = ", ".join(f"'{s}'" for s in SPECIALIST_SLUGS)
    op.execute(f"""
        UPDATE chatbots
        SET is_active = true
        WHERE slug IN ({in_list})
    """)
    op.execute("""
        INSERT INTO feature_credit_costs (id, feature_key, display_name, module_name, base_credits, description, is_active)
        SELECT gen_random_uuid(), 'chatbot_capability', 'Chatbot tool', 'AI Chatbots', 4,
               'Run a subject specialist tool or analysis action', true
        WHERE NOT EXISTS (
            SELECT 1 FROM feature_credit_costs WHERE feature_key = 'chatbot_capability'
        )
    """)


def downgrade() -> None:
    in_list = ", ".join(f"'{s}'" for s in SPECIALIST_SLUGS)
    op.execute(f"""
        UPDATE chatbots
        SET is_active = false
        WHERE slug IN ({in_list})
    """)
    op.execute("DELETE FROM feature_credit_costs WHERE feature_key = 'chatbot_capability'")
