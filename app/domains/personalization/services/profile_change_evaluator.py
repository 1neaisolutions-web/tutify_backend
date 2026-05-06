"""Evaluates severity of profile field changes to determine personalization action."""
from __future__ import annotations

from typing import Any

from app.domains.personalization.enums import ProfileChangeSeverity

# Fields whose change triggers full pipeline reset + slate rebuild.
# curriculum_framework is here because it directly changes pedagogical lens
# used by the content scoring engine.
MAJOR_FIELDS = frozenset({"country", "subjects", "grade_band", "school_type", "curriculum_framework"})

# Fields whose change triggers feature re-rank + partial content gen (lower cost).
MINOR_FIELDS = frozenset(
    {
        "region",
        "years_experience",
        "language_preference",
        "city",
        "postal_code",
        "school_name",
        "identity_fingerprint",
    }
)


class ProfileChangeEvaluator:
    """Classifies profile field changes as none / minor_recompute / major_reset."""

    def evaluate(
        self,
        old_profile: dict[str, Any],
        new_profile: dict[str, Any],
    ) -> tuple[ProfileChangeSeverity, list[str]]:
        """
        Returns (severity, list_of_changed_fields).
        """
        changed_fields: list[str] = []
        has_major = False
        has_minor = False

        all_keys = set(old_profile.keys()) | set(new_profile.keys())
        for key in all_keys:
            old_val = old_profile.get(key)
            new_val = new_profile.get(key)
            if old_val == new_val:
                continue

            changed_fields.append(key)

            if key in MAJOR_FIELDS:
                has_major = True
            elif key == "professional_goals":
                # Addition is minor, removal of goals is major
                old_goals = set(old_val or [])
                new_goals = set(new_val or [])
                if old_goals - new_goals:
                    has_major = True  # Goals removed
                else:
                    has_minor = True  # Goals only added
            elif key in MINOR_FIELDS:
                has_minor = True

        if has_major:
            return ProfileChangeSeverity.MAJOR_RESET, changed_fields
        elif has_minor:
            return ProfileChangeSeverity.MINOR_RECOMPUTE, changed_fields
        elif changed_fields:
            return ProfileChangeSeverity.MINOR_RECOMPUTE, changed_fields
        return ProfileChangeSeverity.NONE, []

    def severity_message(self, severity: ProfileChangeSeverity, changed_fields: list[str]) -> str:
        if severity == ProfileChangeSeverity.NONE:
            return "No personalization changes needed."
        if severity == ProfileChangeSeverity.MINOR_RECOMPUTE:
            return f"Your recommendations will be updated based on changed fields: {', '.join(changed_fields)}."
        return (
            f"Significant profile changes detected ({', '.join(changed_fields)}). "
            "Your personalization will be reset and regenerated. All previous progress is preserved."
        )
