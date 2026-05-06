"""Resolve library `video_id` into fields validated by YouTube quiz request (no UI logic)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.domains.video_library.mapping import subject_lens_for_granular
from app.domains.video_library.schemas import LibraryVideo, VideoLibraryFile


def _normalize_best_quiz_type(text: str) -> str:
    return (text or "").lower()


def derive_learning_focus_and_styles(best_quiz_type: str) -> Tuple[str, List[str]]:
    from app.domains.youtube_quiz.schemas import LEARNING_FOCUS_AREAS, QUESTION_STYLES

    t = _normalize_best_quiz_type(best_quiz_type)
    styles: List[str] = []

    if "vocabulary" in t:
        lf = "Vocabulary development"
    elif "lab" in t or "procedure" in t:
        lf = "Lab skills & procedures"
    elif "critical" in t or "analysis" in t:
        lf = "Critical analysis"
    elif "project" in t or "reflection" in t:
        lf = "Project reflection"
    else:
        lf = "Concept comprehension"

    if lf not in LEARNING_FOCUS_AREAS:
        lf = "Concept comprehension"

    order = [
        ("multiple choice", "Multiple choice"),
        ("multiple", "Multiple choice"),
        ("quick check", "Quick check"),
        ("quick", "Quick check"),
        ("discussion", "Discussion prompt"),
        ("higher-order", "Higher-order thinking"),
        ("higher order", "Higher-order thinking"),
        ("higher", "Higher-order thinking"),
        ("open-ended", "Discussion prompt"),
        ("open ended", "Discussion prompt"),
        ("true false", "Quick check"),
        ("true/false", "Quick check"),
    ]
    for needle, label in order:
        if needle in t and label not in styles:
            styles.append(label)

    if not styles:
        styles = ["Multiple choice", "Higher-order thinking"]

    styles = [s for s in styles if s in QUESTION_STYLES]
    if not styles:
        styles = ["Multiple choice", "Higher-order thinking"]

    return lf, styles


def find_video_in_library(library: VideoLibraryFile, video_id: str) -> Tuple[LibraryVideo, str, str] | None:
    """Return (video, channel_id, channel_name) or None."""
    for subj_key, bucket in library.subjects.items():
        for ch in bucket.channels:
            for v in ch.videos:
                if v.id == video_id:
                    return v, ch.id, ch.name
    return None


def build_overrides_from_video(video: LibraryVideo) -> Dict[str, Any]:
    lf, styles = derive_learning_focus_and_styles(video.bestQuizType)
    return {
        "video_url": video.youtubeUrl,
        "grade_band": video.gradeBand,
        "subject_lens": subject_lens_for_granular(video.subject),
        "learning_focus": lf,
        "question_styles": styles,
    }


def apply_video_id_to_request_dict(data: Dict[str, Any], library: VideoLibraryFile) -> Dict[str, Any]:
    """Merge library fields when `videoId` / `video_id` is present; strip id keys from output dict."""
    out = dict(data)
    vid = out.get("video_id") or out.get("videoId")
    if not vid:
        return out
    found = find_video_in_library(library, str(vid))
    if not found:
        raise ValueError(f"Unknown video library id: {vid}")
    video, _, _ = found
    overrides = build_overrides_from_video(video)
    out.update(overrides)
    out.pop("video_id", None)
    out.pop("videoId", None)
    return out
