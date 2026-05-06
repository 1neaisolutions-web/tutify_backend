"""seed_teacher_tool_feature_costs

Revision ID: b7c8d9e0f1a2
Revises: 4d20b4d74ac7
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "4d20b4d74ac7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO feature_credit_costs
            (id, feature_key, display_name, module_name, base_credits, description, is_active)
        VALUES
            (gen_random_uuid(), 'exam_generate', 'Exam Creation', 'Teacher Tools', 10,
             'Generate a full exam', true),
            (gen_random_uuid(), 'quiz_regenerate_question', 'Quiz – Regenerate Question', 'Teacher Tools', 2,
             'Regenerate a single quiz question', true),
            (gen_random_uuid(), 'assignment_regenerate_topic', 'Assignment – Regenerate Topic', 'Teacher Tools', 2,
             'Regenerate an assignment topic section', true),
            (gen_random_uuid(), 'assignment_regenerate_line', 'Assignment – Regenerate Line', 'Teacher Tools', 2,
             'Regenerate an assignment line item', true),
            (gen_random_uuid(), 'worksheet_regenerate_block', 'Worksheet – Regenerate Block', 'Teacher Tools', 2,
             'Regenerate a worksheet block', true),
            (gen_random_uuid(), 'exam_regenerate_mcq', 'Exam – Regenerate MCQ', 'Teacher Tools', 2,
             'Regenerate an exam multiple-choice question', true),
            (gen_random_uuid(), 'exam_regenerate_short', 'Exam – Regenerate Short Q', 'Teacher Tools', 2,
             'Regenerate an exam short answer', true),
            (gen_random_uuid(), 'exam_regenerate_long', 'Exam – Regenerate Long Q', 'Teacher Tools', 2,
             'Regenerate an exam long answer', true)
        ON CONFLICT (feature_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM feature_credit_costs
        WHERE feature_key IN (
            'exam_generate',
            'quiz_regenerate_question',
            'assignment_regenerate_topic',
            'assignment_regenerate_line',
            'worksheet_regenerate_block',
            'exam_regenerate_mcq',
            'exam_regenerate_short',
            'exam_regenerate_long'
        )
        """
    )
