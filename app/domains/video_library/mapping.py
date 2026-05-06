"""
Profile subject slugs (teacher metadata) → library subject keys and granular labels → quiz subject_lens.
"""

from __future__ import annotations

from typing import FrozenSet, Iterable

# Top-level keys in video_library.json "subjects" object
LIBRARY_SUBJECT_MATHEMATICS = "Mathematics"
LIBRARY_SUBJECT_SCIENCE_STEM = "Science_STEM"
LIBRARY_SUBJECT_SOCIAL_SCIENCES = "Social_Sciences"
LIBRARY_SUBJECT_ELA = "English_Language_Arts"
LIBRARY_SUBJECT_CREATIVE_ARTS = "Creative_Arts"
LIBRARY_SUBJECT_COMPUTER_SCIENCE = "Computer_Science"

# Granular labels stored on each video (must match generator / JSON)
GRANULAR_TO_SUBJECT_LENS: dict[str, str] = {
    "Mathematics": "Mathematics",
    "Algebra": "Mathematics",
    "Geometry": "Mathematics",
    "Biology": "Science & STEM",
    "Chemistry": "Science & STEM",
    "Physics": "Science & STEM",
    "Earth Science": "Science & STEM",
    "History": "Social Sciences",
    "Geography": "Social Sciences",
    "Civics": "Social Sciences",
    "Economics": "Social Sciences",
    "English Language Arts": "English Language Arts",
    "Reading": "English Language Arts",
    "Writing": "English Language Arts",
    "Art": "Creative Arts & Media",
    "Music": "Creative Arts & Media",
    "Theater": "Creative Arts & Media",
    "Computer Science": "Career & Technical Education",
    "Digital Literacy": "Career & Technical Education",
}

# Metadata subject values (slug) → library subject keys used for filtering recommendations
PROFILE_SLUG_TO_LIBRARY_KEYS: dict[str, tuple[str, ...]] = {
    "math": (LIBRARY_SUBJECT_MATHEMATICS,),
    "science": (LIBRARY_SUBJECT_SCIENCE_STEM,),
    "ela": (LIBRARY_SUBJECT_ELA,),
    "social_studies": (LIBRARY_SUBJECT_SOCIAL_SCIENCES,),
    "history": (LIBRARY_SUBJECT_SOCIAL_SCIENCES,),
    "geography": (LIBRARY_SUBJECT_SOCIAL_SCIENCES,),
    "art": (LIBRARY_SUBJECT_CREATIVE_ARTS,),
    "music": (LIBRARY_SUBJECT_CREATIVE_ARTS,),
    "computer_science": (LIBRARY_SUBJECT_COMPUTER_SCIENCE,),
    "foreign_language": (LIBRARY_SUBJECT_ELA,),  # closest lens for language teaching
    "pe": (LIBRARY_SUBJECT_SCIENCE_STEM,),  # health/bio adjacent pool
    "other": (
        LIBRARY_SUBJECT_MATHEMATICS,
        LIBRARY_SUBJECT_SCIENCE_STEM,
        LIBRARY_SUBJECT_SOCIAL_SCIENCES,
        LIBRARY_SUBJECT_ELA,
    ),
}


def library_keys_for_profile_slugs(slugs: Iterable[str]) -> list[str]:
    """Resolve teacher profile subject slugs to library `subjects` keys (deduped, stable order)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in slugs:
        key = (raw or "").strip().lower()
        if not key:
            continue
        for lib_key in PROFILE_SLUG_TO_LIBRARY_KEYS.get(key, PROFILE_SLUG_TO_LIBRARY_KEYS["other"]):
            if lib_key not in seen:
                seen.add(lib_key)
                out.append(lib_key)
    return out


def subject_lens_for_granular(granular: str) -> str:
    """Map video's granular `subject` field to quiz `subject_lens` enum."""
    g = (granular or "").strip()
    return GRANULAR_TO_SUBJECT_LENS.get(g, "Science & STEM")


def all_library_subject_keys() -> FrozenSet[str]:
    return frozenset(
        {
            LIBRARY_SUBJECT_MATHEMATICS,
            LIBRARY_SUBJECT_SCIENCE_STEM,
            LIBRARY_SUBJECT_SOCIAL_SCIENCES,
            LIBRARY_SUBJECT_ELA,
            LIBRARY_SUBJECT_CREATIVE_ARTS,
            LIBRARY_SUBJECT_COMPUTER_SCIENCE,
        }
    )
