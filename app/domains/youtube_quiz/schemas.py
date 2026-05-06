"""
Schemas for YouTube quiz generation endpoint.
"""
from datetime import datetime
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


GRADE_BANDS = {
    "Grades 3-5",
    "Grades 6-8",
    "Grades 9-10",
    "Grades 11-12",
    "Higher Education",
}

SUBJECT_LENSES = {
    "Science & STEM",
    "Mathematics",
    "English Language Arts",
    "Social Sciences",
    "Creative Arts & Media",
    "Career & Technical Education",
}

LEARNING_FOCUS_AREAS = {
    "Concept comprehension",
    "Vocabulary development",
    "Critical analysis",
    "Lab skills & procedures",
    "Project reflection",
}

QUIZ_LANGUAGES = {"English", "Spanish", "French", "Arabic", "Hindi"}

QUESTION_STYLES = {
    "Multiple choice",
    "Higher-order thinking",
    "Quick check",
    "Discussion prompt",
}

QUESTION_STYLE_TO_KEY = {
    "Multiple choice": "multiple_choice",
    "Higher-order thinking": "higher_order",
    "Quick check": "quick_check",
    "Discussion prompt": "discussion_prompt",
}

QuestionStyle = Literal["multiple_choice", "higher_order", "quick_check", "discussion_prompt"]
QuickCheckResponseType = Literal["one_word", "short_phrase", "true_false"]


class YouTubeQuizGenerateRequest(BaseModel):
    """Request payload for quiz generation from a YouTube video."""

    model_config = ConfigDict(populate_by_name=True)

    video_url: str = Field(..., min_length=10)
    grade_band: str
    subject_lens: str
    learning_focus: str
    quiz_language: str
    question_styles: List[str] = Field(default_factory=list)
    question_count: int = Field(..., ge=4, le=12)
    lesson_strategy_id: Optional[str] = None
    difficultyLevel: Optional[Literal["easy", "medium", "challenging"]] = None
    accessibilityMode: bool = False
    video_id: Optional[str] = Field(None, alias="videoId")

    @model_validator(mode="before")
    @classmethod
    def _resolve_library_video_id(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if not (data.get("video_id") or data.get("videoId")):
            return data
        from app.domains.video_library.quiz_merge import apply_video_id_to_request_dict
        from app.domains.video_library.service import load_library

        return apply_video_id_to_request_dict(data, load_library())

    @field_validator("video_url")
    @classmethod
    def validate_video_url(cls, value: str) -> str:
        from app.domains.youtube_quiz.service import YouTubeQuizService

        if not YouTubeQuizService.extract_video_id(value):
            raise ValueError("Invalid YouTube URL. Use watch/share/shorts URL formats.")
        return value

    @field_validator("grade_band")
    @classmethod
    def validate_grade_band(cls, value: str) -> str:
        if value not in GRADE_BANDS:
            raise ValueError(f"Unsupported grade_band: {value}")
        return value

    @field_validator("subject_lens")
    @classmethod
    def validate_subject_lens(cls, value: str) -> str:
        if value not in SUBJECT_LENSES:
            raise ValueError(f"Unsupported subject_lens: {value}")
        return value

    @field_validator("learning_focus")
    @classmethod
    def validate_learning_focus(cls, value: str) -> str:
        if value not in LEARNING_FOCUS_AREAS:
            raise ValueError(f"Unsupported learning_focus: {value}")
        return value

    @field_validator("quiz_language")
    @classmethod
    def validate_quiz_language(cls, value: str) -> str:
        if value not in QUIZ_LANGUAGES:
            raise ValueError(f"Unsupported quiz_language: {value}")
        return value

    @field_validator("question_styles")
    @classmethod
    def validate_question_styles(cls, value: List[str]) -> List[str]:
        invalid_styles = [style for style in value if style not in QUESTION_STYLES]
        if invalid_styles:
            raise ValueError(f"Unsupported question styles: {', '.join(invalid_styles)}")
        return value


class YouTubeQuizSection(BaseModel):
    """One quiz output section."""

    heading: str
    details: str
    questions: List["YouTubeQuizQuestion"] = Field(default_factory=list)


class YouTubeQuizQuestion(BaseModel):
    """One typed quiz question with style-aware fields."""

    id: str = Field(..., min_length=1)
    style: QuestionStyle
    prompt: str = Field(..., min_length=1)
    options: Optional[List[str]] = None
    correct_option_index: Optional[int] = None
    sample_answer: Optional[str] = None
    rubric_points: Optional[List[str]] = None
    expected_response_type: Optional[QuickCheckResponseType] = None
    answer: Optional[Union[str, bool]] = None

    @model_validator(mode="after")
    def validate_style_specific_fields(self) -> "YouTubeQuizQuestion":
        if self.style == "multiple_choice":
            if not self.options or len(self.options) != 4:
                raise ValueError("Multiple choice questions require exactly 4 options.")
            if self.correct_option_index is None:
                raise ValueError("Multiple choice questions require correct_option_index.")
            if self.correct_option_index < 0 or self.correct_option_index >= len(self.options):
                raise ValueError("correct_option_index must reference one of the 4 options.")

        if self.style in {"higher_order", "discussion_prompt"}:
            if not self.sample_answer or not self.sample_answer.strip():
                raise ValueError(f"{self.style} questions require sample_answer.")
            if not self.rubric_points or len([item for item in self.rubric_points if item.strip()]) == 0:
                raise ValueError(f"{self.style} questions require non-empty rubric_points.")

        if self.style == "quick_check":
            if self.expected_response_type is None:
                raise ValueError("quick_check questions require expected_response_type.")
            if self.answer is None:
                raise ValueError("quick_check questions require answer.")
            if self.expected_response_type == "true_false" and not isinstance(self.answer, bool):
                raise ValueError("quick_check true_false answers must be boolean.")
            if self.expected_response_type in {"one_word", "short_phrase"} and not isinstance(self.answer, str):
                raise ValueError("quick_check text response answers must be string.")

        return self


class YouTubeQuizGenerateResponse(BaseModel):
    """Response shape expected by frontend quiz preview state."""

    id: str | None = None
    title: str
    summary: str
    sections: List[YouTubeQuizSection]


class YoutubeQuizGenerationDetailResponse(YouTubeQuizGenerateResponse):
    """Persisted generation row including request metadata."""

    video_url: str
    grade_band: str
    subject_lens: str
    learning_focus: str
    quiz_language: str
    question_count: int
    created_at: datetime
