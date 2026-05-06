"""
Adapter: build Pipeline2 Teacher_profile text from DB feature snapshot (V1).

Used by Learning Hub / Pipeline2IntegrationService to run inference from
teacher_intelligence feature snapshots without rewriting the CSV/CLI path.

Does NOT modify dataset.py or the CSV load path. Additive only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Cluster → Persona mapping (K-max=15, covers all possible cluster labels).
# These are education-domain personas derived from the feature dimensions that
# Pipeline2 clusters on: subject, grade_band, years_experience, school_type,
# region, curriculum, education_level. They are deterministic and stable across
# model versions as long as K ≤ 15.
# ---------------------------------------------------------------------------
CLUSTER_PERSONA_MAP: Dict[int, Dict[str, Any]] = {
    0: {
        "tag": "Foundational Skills Builder",
        "description": "Early-career teacher developing core classroom craft.",
        "top_gaps": ["classroom_management", "formative_assessment", "lesson_planning"],
        "recommended_targets": ["micro_course:classroom_management", "micro_course:formative_assessment"],
    },
    1: {
        "tag": "Veteran Curriculum Leader",
        "description": "Experienced educator with deep curriculum expertise and mentorship focus.",
        "top_gaps": ["technology_integration", "inclusive_practices", "data_literacy"],
        "recommended_targets": ["micro_course:edtech_integration", "tutorial:peer_mentoring"],
    },
    2: {
        "tag": "Technology-Forward Innovator",
        "description": "Tech-savvy teacher integrating digital tools and blended learning.",
        "top_gaps": ["digital_citizenship", "ai_tools_for_teaching", "learning_analytics"],
        "recommended_targets": ["micro_course:ai_tools_for_lesson_planning", "tutorial:blended_learning"],
    },
    3: {
        "tag": "STEM Specialist",
        "description": "Math and science educator focused on inquiry and problem-solving.",
        "top_gaps": ["inquiry_based_learning", "stem_assessment", "real_world_applications"],
        "recommended_targets": ["micro_course:inquiry_based_learning", "tutorial:stem_problem_solving"],
    },
    4: {
        "tag": "Literacy Champion",
        "description": "Language arts and reading specialist supporting comprehension and fluency.",
        "top_gaps": ["reading_comprehension_strategies", "writing_instruction", "vocabulary_development"],
        "recommended_targets": ["micro_course:reading_strategies", "tutorial:writing_workshop"],
    },
    5: {
        "tag": "Early Childhood Expert",
        "description": "K–3 educator specialising in foundational learning and play-based approaches.",
        "top_gaps": ["social_emotional_learning", "phonics_instruction", "play_based_learning"],
        "recommended_targets": ["micro_course:sel_foundations", "tutorial:early_literacy"],
    },
    6: {
        "tag": "Secondary Subject Specialist",
        "description": "High school departmental teacher with deep disciplinary knowledge.",
        "top_gaps": ["exam_preparation", "higher_order_thinking", "student_motivation"],
        "recommended_targets": ["micro_course:differentiation_made_simple", "tutorial:engaging_reluctant_learners"],
    },
    7: {
        "tag": "Inclusion & Differentiation Expert",
        "description": "Educator serving diverse learning needs with adaptive instruction.",
        "top_gaps": ["universal_design_for_learning", "iep_integration", "co_teaching_strategies"],
        "recommended_targets": ["micro_course:differentiation_made_simple", "tutorial:inclusive_classroom"],
    },
    8: {
        "tag": "Assessment & Data-Driven Educator",
        "description": "Teacher using data and evidence to drive instructional decisions.",
        "top_gaps": ["formative_feedback_loops", "data_analysis_for_teachers", "standards_alignment"],
        "recommended_targets": ["micro_course:formative_assessment_strategies", "tutorial:data_informed_teaching"],
    },
    9: {
        "tag": "Project-Based Learning Advocate",
        "description": "Inquiry and PBL practitioner building authentic real-world tasks.",
        "top_gaps": ["pbl_design", "collaborative_learning_structures", "authentic_assessment"],
        "recommended_targets": ["micro_course:pbl_basics", "tutorial:collaborative_classrooms"],
    },
    10: {
        "tag": "Multilingual & International Educator",
        "description": "Teacher supporting English language learners and multilingual classrooms.",
        "top_gaps": ["ell_strategies", "sheltered_instruction", "cultural_responsiveness"],
        "recommended_targets": ["micro_course:ell_classroom_strategies", "tutorial:culturally_responsive_teaching"],
    },
    11: {
        "tag": "Arts & Humanities Educator",
        "description": "Creative teacher integrating arts, culture, and critical thinking.",
        "top_gaps": ["arts_integration", "critical_media_literacy", "interdisciplinary_planning"],
        "recommended_targets": ["micro_course:arts_integration", "tutorial:interdisciplinary_units"],
    },
    12: {
        "tag": "Wellbeing & Whole-Child Educator",
        "description": "Educator prioritising student wellbeing, physical health, and social skills.",
        "top_gaps": ["trauma_informed_practice", "mindfulness_in_class", "physical_activity_integration"],
        "recommended_targets": ["micro_course:sel_for_teachers", "tutorial:trauma_informed_teaching"],
    },
    13: {
        "tag": "Career & Technical Education Specialist",
        "description": "CTE teacher linking academic content to industry and workforce readiness.",
        "top_gaps": ["work_based_learning", "industry_partnerships", "competency_based_assessment"],
        "recommended_targets": ["micro_course:cte_authentic_tasks", "tutorial:work_integrated_learning"],
    },
    14: {
        "tag": "Leadership & Mentoring Educator",
        "description": "Senior educator with coaching, leadership, and instructional mentoring focus.",
        "top_gaps": ["instructional_coaching", "professional_learning_communities", "change_leadership"],
        "recommended_targets": ["micro_course:instructional_coaching_basics", "tutorial:leading_plc"],
    },
}

_DEFAULT_PERSONA = {
    "tag": "Professional Educator",
    "description": "Dedicated educator committed to continuous professional growth.",
    "top_gaps": ["formative_assessment", "differentiation", "classroom_management"],
    "recommended_targets": [],
}


def get_persona_for_cluster(cluster_label: int) -> Dict[str, Any]:
    """Return the persona dict for a given cluster label (0-14). Safe for any int."""
    return CLUSTER_PERSONA_MAP.get(int(cluster_label), _DEFAULT_PERSONA)


def snapshot_features_to_teacher_profile(features: Dict[str, Any]) -> str:
    """
    Build a single Teacher_profile-style text from a DB feature snapshot dict.

    The result is compatible with Pipeline2Model.predict() which expects
    a DataFrame with a Teacher_profile column. This string is used as that
    single row so the same embedding + KMeans path runs unchanged.

    Features dict is the teacher_intelligence feature snapshot schema (V1):
    country, region, subject_primary, grade_band, curriculum_framework,
    years_experience_bucket, certifications_count, education_level,
    experience_records, school_type, has_resume, has_portfolio.
    """
    subject = str(features.get("subject_primary") or "unknown")
    grade = str(features.get("grade_band") or "unknown")
    years = str(features.get("years_experience_bucket") or "unknown")
    school_type = str(features.get("school_type") or "unknown")
    region = str(features.get("region") or "unknown")
    curriculum = str(features.get("curriculum_framework") or "unknown")
    education_level = str(features.get("education_level") or "unknown")
    exp_records = int(features.get("experience_records") or 0)
    certs = int(features.get("certifications_count") or 0)

    return (
        f"Teaches {subject} to {grade} grade. "
        f"Years experience: {years}. "
        f"School type: {school_type}. "
        f"Region: {region}. "
        f"Curriculum: {curriculum}. "
        f"Education level: {education_level}. "
        f"Experience records: {exp_records}. "
        f"Certifications: {certs}."
    )
