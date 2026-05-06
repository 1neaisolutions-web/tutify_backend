"""
Convert TOON/JSON lesson plan data to markdown format for streaming display.
Similar to Activity's lesson_plan_to_markdown function.

Provides:
- dict_to_markdown: generic converter that walks any dict (key -> heading, value -> content).
- universal_output_to_markdown: legacy converter for the fixed universal output shape.
"""
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _humanize_key(key: str) -> str:
    """Turn schema key into a readable heading (e.g. learning_goals -> Learning Goals)."""
    return key.replace("_", " ").strip().title()


def humanize_key(key: str) -> str:
    """Public alias for _humanize_key (section labels)."""
    return _humanize_key(key)


def section_label_from_schema(section_key: str, output_schema: Optional[Dict[str, Any]] = None) -> str:
    """Preferred section label: from output_schema property title, else humanized key."""
    if output_schema and isinstance(output_schema, dict):
        props = output_schema.get("properties") or {}
        if isinstance(props, dict):
            prop = props.get(section_key)
            if isinstance(prop, dict):
                title = prop.get("title")
                if isinstance(title, str) and title.strip():
                    return title.strip()
    return _humanize_key(section_key)


def _value_to_markdown(value: Any, parent_heading_level: int = 0) -> List[str]:
    """
    Convert a single value to markdown lines. parent_heading_level is used for nested dicts.
    """
    lines: List[str] = []

    if value is None:
        return []
    if isinstance(value, bool):
        return ["Yes" if value else "No"]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    lines.append(f"- {text}")
            elif isinstance(item, dict):
                lines.append("")
                lines.extend(_dict_to_markdown_lines(item, parent_heading_level + 1))
            else:
                lines.append(f"- {item}")
        return lines
    if isinstance(value, dict):
        lines.extend(_dict_to_markdown_lines(value, parent_heading_level + 1))
        return lines
    return [str(value)]


def _dict_to_markdown_lines(data: Dict[str, Any], heading_level: int = 0) -> List[str]:
    """
    Walk a dict and produce markdown lines. Each key becomes a heading; value is rendered
    as paragraph, bullets, or nested structure. Skips None and empty strings.
    """
    lines: List[str] = []
    for key, value in list(data.items()):
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        heading = _humanize_key(key)
        prefix = "#" * (heading_level + 1) + " "
        lines.append("")
        lines.append(f"{prefix}{heading}")
        lines.append("")
        chunk = _value_to_markdown(value, heading_level)
        if chunk:
            lines.extend(chunk)
        else:
            if isinstance(value, dict):
                lines.extend(_dict_to_markdown_lines(value, heading_level + 1))
            elif isinstance(value, list) and value:
                for item in value:
                    if isinstance(item, dict):
                        lines.extend(_dict_to_markdown_lines(item, heading_level + 1))
                    elif isinstance(item, str) and item.strip():
                        lines.append(f"- {item.strip()}")
            elif isinstance(value, str) and value.strip():
                lines.append(value.strip())
    return lines


def section_value_to_markdown_text(value: Any) -> str:
    """
    Convert a single section value (string, list, dict, etc.) to markdown text.
    Used for section-by-section streaming: no top-level heading, just content lines.
    Never returns raw JSON: if value is a string that looks like JSON, parse and convert to markdown.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                parsed = json.loads(s)
                value = parsed
            except Exception:
                pass
    lines = _value_to_markdown(value, parent_heading_level=0)
    return "\n".join(lines).strip() if lines else ""


def dict_to_markdown(data: Dict[str, Any]) -> str:
    """
    Convert any output dictionary to markdown (generic, schema-agnostic).

    - Each key becomes a heading (e.g. challenge_title -> ## Challenge Title).
    - String values become paragraphs; list of strings become bullets.
    - Nested objects and list-of-objects get sub-headings and content.
    Works for any template output shape (lesson plan, STEAM challenge, etc.).
    """
    if not data or not isinstance(data, dict):
        logger.warning("dict_to_markdown: invalid data (expected non-empty dict)")
        return ""
    lines = _dict_to_markdown_lines(data, heading_level=0)
    return "\n".join(lines).strip() if lines else ""


def universal_output_to_markdown(data: Dict[str, Any]) -> str:
    """
    Convert UniversalTemplateOutput (from TOON/JSON) to markdown format for streaming.
    
    Works with plain dicts - no Pydantic models required.
    Creates detailed, professional markdown like Activity.
    """
    if not data or not isinstance(data, dict):
        logger.error("Invalid data: must be a dict")
        logger.error(f"Data type: {type(data)}, value: {str(data)[:200]}")
        return ""
    
    # Log for debugging
    logger.info(f"Converting to markdown. Data keys: {list(data.keys())}")
    logger.info(f"Overview preview: {str(data.get('overview', ''))[:100] if data.get('overview') else 'None'}")
    logger.info(f"Learning goals count: {len(data.get('learning_goals', [])) if isinstance(data.get('learning_goals'), list) else 0}")
    logger.info(f"Materials count: {len(data.get('materials', [])) if isinstance(data.get('materials'), list) else 0}")
    
    lines = []
    
    # Extract basic fields with validation
    title = data.get("title") or data.get("topic", "Lesson Plan")
    if not title or not isinstance(title, str) or len(title.strip()) < 3:
        title = "Lesson Plan"
    title = str(title).strip()
    
    overview = data.get("overview", "")
    if overview:
        if isinstance(overview, str):
            overview = overview.strip()
        else:
            overview = str(overview).strip()
        
        # CRITICAL: Filter out incomplete/malformed overview
        # Must be a complete, meaningful sentence
        if overview:
            # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
            # Remove "#" and "##" that appear in the middle (not at start of line)
            overview = overview.replace('##', '').replace('#', '').strip()
            
            word_count = len(overview.split())
            has_balanced_brackets = (overview.count('(') == overview.count(')') and 
                                   overview.count('[') == overview.count(']') and
                                   overview.count('{') == overview.count('}'))
            ends_properly = not overview.endswith(('(', '[', '{', '-', '_', ',', ':', ';', ' '))
            
            if (len(overview) < 30 or  # Too short (increased from 20)
                not has_balanced_brackets or  # Unbalanced brackets
                not ends_properly or  # Incomplete punctuation
                word_count < 8):  # Too few words (increased from 5)
                logger.warning(f"Filtering incomplete overview: length={len(overview)}, words={word_count}, balanced={has_balanced_brackets}, preview={overview[:100]}")
                overview = ""
            else:
                logger.info(f"Valid overview: length={len(overview)}, words={word_count}")
    else:
        overview = ""
    
    learning_goals = data.get("learning_goals", [])
    if not isinstance(learning_goals, list):
        learning_goals = []
    # Filter out invalid goals - must be complete, meaningful sentences
    valid_goals = []
    for g in learning_goals:
        if g:
            goal_str = str(g).strip() if isinstance(g, str) else str(g).strip()
            # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
            goal_str = goal_str.replace('##', '').replace('#', '').strip()
            
            word_count = len(goal_str.split())
            has_balanced = (goal_str.count('(') == goal_str.count(')') and 
                          goal_str.count('[') == goal_str.count(']'))
            ends_properly = not goal_str.endswith(('(', '[', '{', '-', '_', ',', ':', ';', ' '))
            
            # CRITICAL: Only add if goal is complete and meaningful
            if (len(goal_str) > 20 and  # At least 20 chars (increased from 15)
                has_balanced and  # Balanced brackets
                ends_properly and  # Not incomplete
                word_count >= 6):  # At least 6 words (increased from 4)
                valid_goals.append(goal_str)
                logger.debug(f"Valid goal: length={len(goal_str)}, words={word_count}")
            else:
                logger.warning(f"Filtering incomplete goal: length={len(goal_str)}, words={word_count}, balanced={has_balanced}, preview={goal_str[:50]}")
    learning_goals = valid_goals
    
    # CRITICAL: If no valid goals, don't show incomplete ones
    if len(learning_goals) == 0:
        logger.warning("No valid learning goals found after filtering")
    
    materials = data.get("materials", [])
    if not isinstance(materials, list):
        materials = []
    # Filter out invalid materials - must be complete strings
    valid_materials = []
    for m in materials:
        if m:
            mat_str = str(m).strip() if isinstance(m, str) else str(m).strip()
            # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
            mat_str = mat_str.replace('##', '').replace('#', '').strip()
            
            has_balanced = (mat_str.count('(') == mat_str.count(')') and 
                          mat_str.count('[') == mat_str.count(']'))
            ends_properly = not mat_str.endswith(('(', '[', '{', '-', '_', ',', ':', ';', ' '))
            
            # CRITICAL: Only add if material is complete and meaningful
            if (len(mat_str) > 3 and  # At least 3 chars (increased from 2)
                has_balanced and  # Balanced brackets
                ends_properly):  # Not incomplete
                valid_materials.append(mat_str)
            else:
                logger.warning(f"Filtering incomplete material: length={len(mat_str)}, balanced={has_balanced}, preview={mat_str[:50]}")
    materials = valid_materials
    
    steps = data.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    # Filter out incomplete steps - must have complete, meaningful content
    valid_steps = []
    for step in steps:
        if step and isinstance(step, dict):
            step_title = step.get("title", "").strip() if step.get("title") else ""
            step_desc = step.get("description", "").strip() if step.get("description") else ""
            
            # Clean and validate title - must be complete
            if step_title:
                step_title = step_title.strip()
                # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
                step_title = step_title.replace('##', '').replace('#', '').strip()
                if (step_title.endswith(('(', '[', '{', '-', '_', ',', ':', ';')) or
                    len(step_title) < 3 or
                    step_title.count('(') != step_title.count(')')):
                    step_title = ""
            
            # Clean and validate description - must be complete sentence
            if step_desc:
                step_desc = step_desc.strip()
                # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
                step_desc = step_desc.replace('##', '').replace('#', '').strip()
                if (step_desc.endswith(('(', '[', '{', '-', '_', ',', ':', ';')) or
                    len(step_desc) < 15 or
                    step_desc.count('(') != step_desc.count(')') or
                    len(step_desc.split()) < 5):  # At least 5 words
                    step_desc = ""
            
            # Only add if step has meaningful, complete content
            if (step_title and len(step_title) > 3) or (step_desc and len(step_desc) > 15):
                valid_steps.append({
                    "title": step_title,
                    "description": step_desc
                })
    steps = valid_steps
    
    differentiation = data.get("differentiation", [])
    if not isinstance(differentiation, list):
        differentiation = []
    differentiation = [d for d in differentiation if d and isinstance(d, str) and len(str(d).strip()) > 10]
    
    assessment = data.get("assessment", {})
    if not isinstance(assessment, dict):
        assessment = {}
    
    teacher_notes = data.get("teacher_notes", [])
    if not isinstance(teacher_notes, list):
        teacher_notes = []
    teacher_notes = [n for n in teacher_notes if n and isinstance(n, str) and len(str(n).strip()) > 10]
    
    lesson_sections = data.get("lesson_sections", [])
    if not isinstance(lesson_sections, list):
        lesson_sections = []
    
    # Title
    lines.append(f"# [Lesson Title: {title}]")
    lines.append("")
    
    # Overview - only add if we have valid, complete overview
    if overview and len(overview) > 30 and len(overview.split()) >= 8:
        lines.append("## OVERVIEW")
        lines.append(overview)
        lines.append("")
    
    # Learning Objective
    lines.append("## LEARNING OBJECTIVE")
    if learning_goals and isinstance(learning_goals, list) and len(learning_goals) > 0:
        # Show first goal as main objective (like Activity)
        first_goal = learning_goals[0] if isinstance(learning_goals[0], str) else learning_goals[0].get("text", str(learning_goals[0]))
        first_goal = first_goal.strip() if isinstance(first_goal, str) else str(first_goal).strip()
        # CRITICAL: Only add if goal is complete and meaningful (at least 20 chars, 6 words)
        if first_goal and len(first_goal) > 20 and len(first_goal.split()) >= 6:
            lines.append(first_goal)
        # Show additional goals if any
        if len(learning_goals) > 1:
            for goal in learning_goals[1:]:
                goal_text = goal if isinstance(goal, str) else goal.get("text", str(goal))
                goal_text = goal_text.strip() if isinstance(goal_text, str) else str(goal_text).strip()
                # CRITICAL: Only add if goal is complete and meaningful
                if goal_text and len(goal_text) > 20 and len(goal_text.split()) >= 6:
                    lines.append(f"- {goal_text}")
    else:
        lines.append("Students will learn and apply key concepts.")
    lines.append("")
    
    # Assessment
    lines.append("## ASSESSMENT")
    if isinstance(assessment, dict):
        overview_text = assessment.get("overview", "")
        if overview_text:
            lines.append(overview_text)
        
        checks = assessment.get("checks_for_understanding", [])
        if checks:
            for check in checks:
                check_text = check if isinstance(check, str) else check.get("text", str(check))
                lines.append(f"- {check_text}")
        
        rubric = assessment.get("rubric")
        if rubric:
            rubric_text = rubric if isinstance(rubric, str) else str(rubric)
            lines.append(f"**Rubric**: {rubric_text}")
    else:
        lines.append("Students will demonstrate understanding through practical application.")
    lines.append("")
    
    # Key Points (if available)
    key_points = data.get("key_points", [])
    if key_points:
        lines.append("## KEY POINTS")
        for point in key_points[:5]:  # Limit to 5 like Activity
            point_text = point if isinstance(point, str) else str(point)
            lines.append(f"- {point_text}")
        lines.append("")
    
    # Lesson Sections (for LESSON_DESIGN category) - PROFESSIONAL DETAIL like Activity
    if lesson_sections and isinstance(lesson_sections, list):
        # Map section IDs to professional titles
        section_title_map = {
            "opening": "OPENING",
            "introduction": "INTRODUCTION TO NEW MATERIAL",
            "guided_practice": "GUIDED PRACTICE",
            "independent_practice": "INDEPENDENT PRACTICE",
            "closing": "CLOSING"
        }
        
        for section in lesson_sections:
            if not isinstance(section, dict):
                continue
                
            section_id = section.get("id", "")
            section_title = section.get("title", section_id)
            section_goal = section.get("goal", "")
            section_steps = section.get("steps", [])
            
            # Use professional title
            professional_title = section_title_map.get(section_id, section_title.upper())
            lines.append(f"## {professional_title}")
            lines.append("")
            
            if section_goal:
                # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
                section_goal_clean = section_goal.strip().replace('##', '').replace('#', '').strip()
                if section_goal_clean and len(section_goal_clean) > 10:
                    lines.append(section_goal_clean)
                    lines.append("")
            
            # Format steps with duration and detail (like Activity)
            for step in section_steps:
                if isinstance(step, dict):
                    step_label = step.get("label", step.get("title", ""))
                    step_duration = step.get("duration", "")
                    step_detail = step.get("detail", step.get("description", ""))
                    
                    # CRITICAL: Clean and validate step content
                    if step_label:
                        step_label = step_label.strip()
                        # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
                        step_label = step_label.replace('##', '').replace('#', '').strip()
                        if (step_label.endswith(('(', '[', '{', '-', '_', ',', ':', ';')) or
                            len(step_label) < 3):
                            step_label = ""
                    
                    if step_detail:
                        step_detail = step_detail.strip()
                        # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
                        step_detail = step_detail.replace('##', '').replace('#', '').strip()
                        if (step_detail.endswith(('(', '[', '{', '-', '_', ',', ':', ';')) or
                            len(step_detail) < 15 or
                            step_detail.count('(') != step_detail.count(')') or
                            len(step_detail.split()) < 5):
                            step_detail = ""
                    
                    # Only add if we have valid, complete content
                    if step_label and step_detail:
                        duration_text = f" ({step_duration})" if step_duration else ""
                        lines.append(f"- **{step_label}{duration_text}**: {step_detail}")
                    elif step_label and len(step_label) > 3:
                        lines.append(f"- **{step_label}**: {step_detail if step_detail else ''}")
            
            lines.append("")
    
    # Steps (if no lesson_sections, use regular steps)
    elif steps and isinstance(steps, list) and len(steps) > 0:
        lines.append("## Steps")
        lines.append("")
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                step_title = step.get("title", f"Step {i}")
                step_description = step.get("description", "")
                
                # CRITICAL: Clean and validate step title
                if step_title:
                    step_title = step_title.strip()
                    # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
                    step_title = step_title.replace('##', '').replace('#', '').strip()
                    if (step_title.endswith(('(', '[', '{', '-', '_', ',', ':', ';')) or
                        len(step_title) < 3 or
                        step_title.count('(') != step_title.count(')')):
                        step_title = f"Step {i}"
                
                # CRITICAL: Clean and validate step description
                if step_description:
                    step_description = step_description.strip()
                    # CRITICAL: Remove any markdown syntax that shouldn't be in the middle of text
                    step_description = step_description.replace('##', '').replace('#', '').strip()
                    if (step_description.endswith(('(', '[', '{', '-', '_', ',', ':', ';')) or
                        len(step_description) < 15 or
                        step_description.count('(') != step_description.count(')') or
                        len(step_description.split()) < 5):
                        step_description = ""
                
                # Only add if we have valid content
                if step_title and len(step_title) > 3:
                    lines.append(f"{i}. **{step_title}**")
                    if step_description and len(step_description) > 15:
                        lines.append(step_description)
                    lines.append("")
            elif isinstance(step, str):
                step_str = step.strip()
                # CRITICAL: Only add if step is complete and meaningful
                if (step_str and len(step_str) > 15 and 
                    not step_str.endswith(('(', '[', '{', '-', '_', ',', ':', ';')) and
                    len(step_str.split()) >= 5):
                    lines.append(f"{i}. {step_str}")
                    lines.append("")
    
    # Materials
    if materials:
        lines.append("## REQUIRED MATERIALS")
        for material in materials:
            if material:  # Skip empty materials
                material_text = material if isinstance(material, str) else str(material)
                # Clean material text - remove extra whitespace and malformed artifacts
                material_text = material_text.strip()
                # Only add if material is meaningful (not just whitespace or delimiters)
                if material_text and len(material_text) > 1:
                    lines.append(f"- {material_text}")
        lines.append("")
    
    # Differentiation
    if differentiation:
        lines.append("## DIFFERENTIATION STRATEGIES")
        for item in differentiation:
            item_text = item if isinstance(item, str) else str(item)
            lines.append(f"- {item_text}")
        lines.append("")
    
    # Extension Activity
    extension = data.get("extension", {})
    if extension:
        if isinstance(extension, dict):
            extension_detail = extension.get("detail", extension.get("title", ""))
            if extension_detail:
                lines.append("## EXTENSION ACTIVITY")
                lines.append(extension_detail)
                lines.append("")
    
    # Homework
    homework = data.get("homework", {})
    if homework:
        if isinstance(homework, dict):
            homework_prompt = homework.get("prompt", homework.get("detail", ""))
            if homework_prompt:
                lines.append("## HOMEWORK")
                lines.append(homework_prompt)
                lines.append("")
    
    # Standards Aligned
    standard = data.get("standard") or data.get("standards_framework")
    constraints = data.get("constraints") or data.get("differentiation_notes", "class constraints")
    subject = data.get("subject", "Subject")
    grade_band = data.get("grade_band", "Grade")
    
    lines.append("## STANDARDS ALIGNED")
    standard_text = f" that align with: {standard}" if standard and str(standard).strip() else ""
    lines.append(f"- **Relevant Standards**: [List applicable educational standards for {subject} at {grade_band} level{standard_text}]")
    lines.append(f"- **Note**: [Adapt materials and recommendations as needed based on: {constraints}]")
    lines.append("")
    
    # Teacher Notes (if available)
    if teacher_notes:
        lines.append("## TEACHER NOTES")
        for note in teacher_notes:
            note_text = note if isinstance(note, str) else str(note)
            lines.append(f"- {note_text}")
        lines.append("")
        # Custom sections (optional - for template-specific headings and content)
    custom_sections = data.get("custom_sections")
    if custom_sections and isinstance(custom_sections, list):
        for section in custom_sections:
            if isinstance(section, dict):
                title = section.get("title") or section.get("heading", "")
                content = section.get("content") or section.get("text", "")
                if title or content:
                    if title:
                        lines.append(f"## {title}")
                    if content:
                        lines.append(str(content).strip())
                    lines.append("")

    return "\n".join(lines).strip()    
    


