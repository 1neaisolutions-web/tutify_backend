"""
Math extraction provider implementations.
Baseline: heuristics + [[MATH]] markers. Mathpix stub for later.
"""
import re
from typing import List

from app.core.logging import get_logger
from app.domains.content_ingestion.providers.base import (
    MathExtractionProvider,
    MathBlock,
    PageText,
)

logger = get_logger(__name__)

# Patterns that suggest math (equations, expressions)
MATH_PATTERNS = [
    r"=",  # equation
    r"\^",  # exponent
    r"√|\\sqrt",  # sqrt
    r"∑|\\sum",  # sum
    r"∫|\\int",  # integral
    r"π|\\pi",  # pi
    r"sin\s*\(",  # sin(
    r"log\s*\(",  # log(
    r"cos\s*\(",  # cos(
    r"x\^2|y\^2",  # x^2
    r"\d+x|\d+\s*x",  # 2x
    r"\d+/\d+",  # fraction a/b
    r"\\frac",
    r"\\frac\{",
]
MATH_REGEX = re.compile("|".join(f"({p})" for p in MATH_PATTERNS))


def compute_math_density(text: str) -> float:
    """Count math-like symbols/patterns; return density (matches per char * 1000)."""
    if not (text or "").strip():
        return 0.0
    matches = len(MATH_REGEX.findall(text))
    return (matches / len(text)) * 1000.0 if text else 0.0


def is_math_line(line: str) -> bool:
    """Heuristic: line looks like math (has = or ^ or fractions or backslash commands)."""
    line = (line or "").strip()
    if len(line) < 2:
        return False
    if "=" in line and len(line) < 120:
        return True
    if re.search(r"\^|√|∑|∫|π|\\frac|sin\s*\(|log\s*\(|cos\s*\(", line):
        return True
    if re.search(r"\d+/\d+", line) and re.search(r"[a-zA-Z]", line):
        return True
    return False


class BaselineMathExtractionProvider(MathExtractionProvider):
    """
    Free baseline: use heuristics to identify math lines and wrap with [[MATH]]...[[/MATH]].
    """
    provider_name = "baseline"

    def validate_config(self) -> bool:
        return True

    def extract_math(
        self,
        document_id: str,
        pages_text: List[PageText],
        **kwargs
    ) -> List[MathBlock]:
        blocks = []
        for pt in pages_text:
            lines = (pt.text or "").split("\n")
            for line in lines:
                if not is_math_line(line):
                    continue
                normalized = line.strip()
                blocks.append(
                    MathBlock(
                        document_id=document_id,
                        page_no=pt.page_no,
                        block_type="equation",
                        raw_text=line,
                        normalized_text=normalized,
                        bbox_json=None,
                        confidence=None,
                        provider_name=self.provider_name,
                    )
                )
        logger.info(f"Baseline math extraction: document={document_id}, blocks={len(blocks)}")
        return blocks

    @staticmethod
    def inject_markers_into_text(page_text: PageText) -> PageText:
        """Return new PageText with [[MATH]]...[[/MATH]] around detected math lines."""
        lines = (page_text.text or "").split("\n")
        out = []
        for line in lines:
            if is_math_line(line):
                out.append(f"[[MATH]] {line.strip()} [[/MATH]]")
            else:
                out.append(line)
        new_text = "\n".join(out)
        return PageText(
            page_no=page_text.page_no,
            text=new_text,
            char_count=len(new_text),
            ocr_confidence=page_text.ocr_confidence,
            ocr_engine=page_text.ocr_engine,
        )
