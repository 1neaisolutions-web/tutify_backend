"""
Fallback provider for tests and failure scenarios.
"""
import json
import re
import asyncio
import time
from typing import Optional, Dict, Any

from app.llm.base import BaseProvider
from app.llm.schemas import LLMResponse, TokenUsage


class FallbackProvider(BaseProvider):
    """Non-network provider for tests/failure fallback."""

    provider_name = "fallback"

    async def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate a deterministic, schema-shaped fallback response.

        Returns:
            LLMResponse with dummy values
        """
        # Simulate some latency
        await asyncio.sleep(0.01)
        
        latency_ms = 10

        # Try to extract topic_text from the worksheet prompt
        topic_text = "the topic"
        m = re.search(r'"topic_text"\s*:\s*"([^"]+)"', prompt)
        if m and m.group(1).strip():
            topic_text = m.group(1).strip()
        else:
            m2 = re.search(r"TOPIC\s*[:\-]\s*(.+)", prompt, flags=re.IGNORECASE)
            if m2:
                topic_text = m2.group(1).strip().strip('"').strip()

        # Try to infer counts (best-effort)
        num_questions = 10
        m3 = re.search(r'"num_questions"\s*:\s*(\d+)', prompt)
        if m3:
            try:
                num_questions = max(1, min(20, int(m3.group(1))))
            except Exception:
                pass

        mcq_count = num_questions // 2
        short_count = num_questions - mcq_count

        wants_analytical = "analytical" in (prompt or "").lower() or "application-based" in (prompt or "").lower()

        questions = []
        qid = 1
        for i in range(mcq_count):
            stem = (
                f"({topic_text}) {('Analyze' if wants_analytical else 'Choose')} the best answer about {topic_text}."
            )
            options = [
                f"A) A statement directly about {topic_text}",
                f"B) A common misconception about {topic_text}",
                f"C) An unrelated concept (not about {topic_text})",
                f"D) A vague statement with no clear link to {topic_text}",
            ]
            questions.append(
                {
                    "question_id": qid,
                    "type": "mcq",
                    "question_text": stem,
                    "options": options,
                    "correct_option": "A",
                    "answer_text": f"{topic_text} is the subject of the question.",
                    "marks": 1,
                    "difficulty": "medium",
                    "math_content": False,
                }
            )
            qid += 1

        for i in range(short_count):
            verb = "Explain and apply" if wants_analytical else "Explain"
            questions.append(
                {
                    "question_id": qid,
                    "type": "short",
                    "question_text": f"({topic_text}) {verb} what {topic_text} means in a real-world workflow.",
                    "answer_text": f"{topic_text} is a process/technique relevant to the prompt context.",
                    "marks": 2,
                    "difficulty": "medium",
                    "math_content": False,
                }
            )
            qid += 1

        content = json.dumps(
            {
                "questions": questions,
                "marking_scheme": [],
            }
        )
        
        return LLMResponse(
            content=content,
            model_used="fallback",
            provider=self.provider_name,
            token_usage=TokenUsage(prompt=0, completion=max(1, len(content) // 4), total=max(1, len(content) // 4)),
            cost_estimate=0.0,
            latency_ms=latency_ms
        )

    def validate_config(self) -> bool:
        """Always returns True (no config needed)."""
        return True

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Return None (no model info for fallback)."""
        return None

