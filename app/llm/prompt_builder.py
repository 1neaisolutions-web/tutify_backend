"""
TOON-aware prompt builder for LLM communication.

Builds prompts with TOON input format and schema instructions for token efficiency.
"""
import json
from typing import Any, Dict, Optional, Tuple

from app.core.logging import get_logger
from app.models.template import TemplateCategory

from app.llm.toon_handler import TOONHandler

logger = get_logger(__name__)


class TOONPromptBuilder:
    """Builds prompts with TOON input format and schema instructions."""

    def __init__(self, toon_handler: Optional[TOONHandler] = None):
        """
        Initialize prompt builder.
        
        Args:
            toon_handler: TOONHandler instance (creates new one if not provided)
        """
        self.toon_handler = toon_handler or TOONHandler()

    def build_prompt(
        self,
        input_data: Dict[str, Any],
        prompt_definition: Dict[str, Any],
        template_category: TemplateCategory,
        model_config: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """
        Build complete prompt with TOON input and output schema.
        Includes language and standard handling like Activity.
        
        Returns:
            Tuple of (system_message, user_prompt)
            
        Process:
        1. Extract language and standard from input_data (like Activity)
        2. Encode input_data to TOON format
        3. Extract TOON schema from prompt_definition
        4. Build system message with TOON instructions and language/standard
        5. Build user prompt with TOON input and schema instructions
        """
        # Extract language and standard (like Activity)
        output_language = input_data.get("output_language", "English")
        language = input_data.get("language")  # For "Other" option
        standard = input_data.get("standard") or input_data.get("standards_framework")
        
        # Handle "Other" language option (like Activity)
        RECOGNIZED_LANGUAGES = {
            "English", "Spanish", "French", "German", "Italian", "Portuguese",
            "Chinese", "Japanese", "Korean", "Russian", "Arabic", "Hindi",
            "Dutch", "Swedish", "Norwegian", "Danish", "Finnish", "Polish",
            "Turkish", "Greek", "Hebrew", "Thai", "Vietnamese", "Indonesian",
            "Czech", "Romanian", "Hungarian", "Bulgarian", "Croatian", "Serbian"
        }
        
        original_language = output_language
        language_note = ""
        if output_language == "Other":
            custom_language = language or "English"
            if not custom_language or custom_language.strip() == "":
                output_language = "English"
                logger.warning("Custom language was empty, defaulting to English")
            else:
                custom_language = custom_language.strip()
                # IMPORTANT: Use custom language even if not recognized (like user requested)
                # Don't fallback to English - let LLM try to generate in requested language
                if custom_language not in RECOGNIZED_LANGUAGES:
                    logger.info(
                        f"Custom language '{custom_language}' is not in recognized list, "
                        f"but will attempt to generate in {custom_language} as requested."
                    )
                    # Still use the custom language - don't fallback
                    output_language = custom_language
                    language_note = f"\n\nNOTE: The language '{custom_language}' may not be fully supported, but will attempt generation in {custom_language}."
                else:
                    output_language = custom_language
        
        # Map language to instruction (extended list)
        language_instructions = {
            "English": "in English",
            "Spanish": "in Spanish (en español)",
            "French": "in French (en français)",
            "German": "in German (auf Deutsch)",
            "Italian": "in Italian (in italiano)",
            "Portuguese": "in Portuguese (em português)",
            "Chinese": "in Chinese (用中文)",
            "Japanese": "in Japanese (日本語で)",
            "Urdu": "in Urdu (اردو میں)",
            "Arabic": "in Arabic (بالعربية)",
            "Hindi": "in Hindi (हिंदी में)",
            "Russian": "in Russian (на русском)",
            "Korean": "in Korean (한국어로)",
        }
        
        # Get instruction or create generic one for unrecognized languages
        lang_instruction = language_instructions.get(output_language)
        if not lang_instruction:
            # For unrecognized languages, create a generic instruction
            lang_instruction = f"in {output_language}"
            logger.info(f"Using generic language instruction for '{output_language}': {lang_instruction}")
        
        # Calculate standard_note BEFORE building system message (needed for user prompt)
        standard_note = ""
        if standard and standard.strip():
            # Check if standard looks valid (basic validation)
            common_standard_prefixes = ["CCSS", "UK", "IB", "AUSTRALIAN", "CANADIAN", "SINGAPORE", "NEXT_GEN"]
            standard_upper = standard.upper().strip()
            is_recognized = any(standard_upper.startswith(prefix) for prefix in common_standard_prefixes)
            
            if not is_recognized:
                standard_note = f"\n\nNOTE: The standard '{standard}' may not be recognized. Please mention this in the STANDARDS ALIGNED section: 'Note: The provided standard '{standard}' may not be recognized or validated. Please adapt materials and recommendations as needed based on the constraints and available resources.'"
        
        # 1. Encode input_data to TOON format (70% token reduction)
        toon_input = self.toon_handler.encode_input(input_data)
        
        # 2. Extract schema type from prompt_definition or template category
        schema_type = self._determine_schema_type(template_category, prompt_definition)
        
        # 3. Build system message with TOON instructions and language/standard
        system_message = self._build_system_message(
            schema_type,
            prompt_definition,
            output_language=output_language,
            lang_instruction=lang_instruction,
            standard=standard,
            output_schema=output_schema,
        )
        
        # 4. Build user prompt with TOON input and schema instructions
        # Extract additional fields for detailed prompt (like Activity)
        topic = input_data.get("topic") or input_data.get("topic_concept") or input_data.get("learning_objective", "")
        subject = input_data.get("subject", "")
        grade_band = input_data.get("grade_band", "")
        available_time = input_data.get("time_duration_minutes") or input_data.get("available_time")
        materials = input_data.get("materials") or input_data.get("available_materials", "")
        constraints = input_data.get("constraints") or input_data.get("differentiation_notes", "")
        
        user_prompt = self._build_user_prompt(
            toon_input, 
            schema_type, 
            prompt_definition,
            input_data=input_data,  # Pass full input_data for assessment-specific fields
            output_language=output_language,
            lang_instruction=lang_instruction,
            language_note=language_note,
            standard=standard,
            standard_note=standard_note,
            topic=topic,
            subject=subject,
            grade_band=grade_band,
            available_time=available_time,
            materials=materials,
            constraints=constraints
        )
        
        return system_message, user_prompt
    
    def build_streaming_prompt(
        self,
        input_data: Dict[str, Any],
        prompt_definition: Dict[str, Any],
        template_category: TemplateCategory,
    ) -> Tuple[str, str]:
        """
        Build prompt for streaming that generates markdown directly (like Activity).
        
        This is different from build_prompt which generates TOON.
        For streaming, we want markdown output for real-time display.
        
        Returns:
            Tuple of (system_message, streaming_prompt)
        """
        # Extract language and standard (same as build_prompt)
        output_language = input_data.get("output_language", "English")
        language = input_data.get("language")  # For "Other" option
        standard = input_data.get("standard") or input_data.get("standards_framework")
        
        # Handle "Other" language option (same logic as build_prompt)
        RECOGNIZED_LANGUAGES = {
            "English", "Spanish", "French", "German", "Italian", "Portuguese",
            "Chinese", "Japanese", "Korean", "Russian", "Arabic", "Hindi",
            "Dutch", "Swedish", "Norwegian", "Danish", "Finnish", "Polish",
            "Turkish", "Greek", "Hebrew", "Thai", "Vietnamese", "Indonesian",
            "Czech", "Romanian", "Hungarian", "Bulgarian", "Croatian", "Serbian"
        }
        
        original_language = output_language
        if output_language == "Other":
            custom_language = language or "English"
            if not custom_language or custom_language.strip() == "":
                output_language = "English"
            else:
                custom_language = custom_language.strip()
                if custom_language not in RECOGNIZED_LANGUAGES:
                    output_language = custom_language  # Use even if not recognized
                else:
                    output_language = custom_language
        
        # Map language to instruction
        language_instructions = {
            "English": "in English",
            "Spanish": "in Spanish (en español)",
            "French": "in French (en français)",
            "German": "in German (auf Deutsch)",
            "Italian": "in Italian (in italiano)",
            "Portuguese": "in Portuguese (em português)",
            "Chinese": "in Chinese (用中文)",
            "Japanese": "in Japanese (日本語で)",
            "Urdu": "in Urdu (اردو میں)",
            "Arabic": "in Arabic (بالعربية)",
            "Hindi": "in Hindi (हिंदी में)",
            "Russian": "in Russian (на русском)",
            "Korean": "in Korean (한국어로)",
        }
        
        lang_instruction = language_instructions.get(output_language)
        if not lang_instruction:
            lang_instruction = f"in {output_language}"
        
        # Extract fields for prompt
        topic = input_data.get("topic") or input_data.get("topic_concept") or input_data.get("learning_objective", "")
        subject = input_data.get("subject", "")
        grade_band = input_data.get("grade_band", "")
        available_time = input_data.get("time_duration_minutes") or input_data.get("available_time")
        materials = input_data.get("materials") or input_data.get("available_materials", "")
        constraints = input_data.get("constraints") or input_data.get("differentiation_notes", "")
        
        # Build TOON input section (extract from regular prompt)
        regular_system, regular_user = self.build_prompt(input_data, prompt_definition, template_category)
        
        # Extract TOON input section (everything before "OUTPUT:")
        toon_input_start = regular_user.find("INPUT (TOON") or regular_user.find("Generate educational content")
        toon_input_end = regular_user.find("OUTPUT:")
        if toon_input_start >= 0 and toon_input_end >= 0:
            toon_input_section = regular_user[toon_input_start:toon_input_end].strip()
        else:
            # Fallback: encode input to TOON
            toon_input = self.toon_handler.encode_input(input_data)
            toon_input_section = f"INPUT (TOON format):\n{toon_input}"
        
        # Build streaming system message (like Activity, but with explicit instructions for complete content)
        streaming_system_message = (
            "You are an expert instructional designer who creates comprehensive, "
            "well-structured lesson plans for educators. "
            "CRITICAL: Always write COMPLETE headers (e.g., '## LEARNING OBJECTIVE' not '##ARNING OBJECTIVE') "
            "and COMPLETE words - never truncate or cut off mid-word. "
            "Write professional, detailed content suitable for international use."
        )
        
        # Build streaming prompt with markdown output instructions (EXACTLY like Activity)
        # Match Activity's prompt structure EXACTLY - no extra instructions that might confuse the LLM
        streaming_prompt = f"""You are an expert instructional designer. Generate a comprehensive, professional lesson plan in the EXACT format specified below.

{toon_input_section}

OUTPUT: Generate a detailed lesson plan following this EXACT structure and format. Write everything {lang_instruction}:

# [Lesson Title: {topic}]

## LEARNING OBJECTIVE

[Write a clear, measurable learning objective. Students will...]

## ASSESSMENT

[Describe how students will demonstrate mastery. Include: working prototype/demonstration, written explanation, rubric-based assessment covering reliability, component interaction, and justification of choices/safety considerations.]

## KEY POINTS

- [Core concept 1: e.g., Fundamentals related to the topic]
- [Core concept 2: e.g., Practical application and hands-on learning]
- [Core concept 3: e.g., Design process and documentation]
- [Core concept 4: e.g., Safety and classroom management]
- [Core concept 5: Add more as appropriate for the topic]

## OPENING

- **Hook (1-2 minutes)**: [Brief video/demo or engaging introduction]
- **Goal Explanation**: [Explain the lesson's goal and what students will accomplish]
- **Group Organization**: [Organize students into groups with assigned roles]
- **Anticipatory Question**: [Pose a question to engage students]

## INTRODUCTION TO NEW MATERIAL

[5-8 minutes per mini-topic]
- **Key Concepts**: [Explain main concepts related to {topic or 'the topic'}]
- **Materials Overview**: [Explain how to use: {materials or "Not specified"}]
- **Basic Principles**: [Explain fundamental principles]
- **Active Learning**: [Include hands-on activity or demonstration]
- **Common Misconception**: [Address a common misconception about the topic]

## GUIDED PRACTICE

- **Behavioral Expectations**: [Set clear expectations for student behavior]
- **Component Identification (5 minutes)**: [Activity to identify key elements]
- **Simple Activity Build (10 minutes)**: [Step-by-step activity building]
- **Practice Exercise (10-15 minutes)**: [Guided practice with teacher support and guiding questions]
- **Task Challenge Introduction (10 minutes)**: [Introduce the main challenge with success criteria and model timeline]
- **Monitoring**: [Use checklist and probing questions to monitor student performance]

## INDEPENDENT PRACTICE

- **Behavioral Expectations**: [Set expectations for collaborative work]
- **Assignment**: [Teams design and complete the main activity]
- **Deliverables**: 
  - Working prototype or completed work
  - One-page design explanation
  - Team demonstration
- **Timeline**: [Adapt for {available_time} minute lesson or split across two class periods]
- **Teacher Support**: [Mini-lessons and rubric for formative feedback]

## CLOSING

- **Exit Activity**: [Quick activity where teams share success/challenge]
- **Restatement**: [Restate learning objective and assessment criteria]

## EXTENSION ACTIVITY

[For early finishers: Add a secondary objective or challenge with documentation and testing]

## HOMEWORK

[Individual reflection/journal on activity behavior, technical challenges, and potential improvements with additional resources]

## STANDARDS ALIGNED

- **Relevant Standards**: [List applicable educational standards for {subject or 'Subject'} at {grade_band or 'Grade'} level{f" that align with: {standard}" if standard and standard.strip() else ""}]
- **Note**: [Adapt materials and recommendations as needed based on: {constraints or "None specified"}]

FINAL REMINDERS:
- Write EVERYTHING in {output_language} - all content, headings, and text
- Use the EXACT materials specified: {materials or "Not specified"}
- Consider these constraints: {constraints or "None specified"}
- Make it appropriate for {grade_band or 'Grade'} grade level and {available_time} minutes duration
- CRITICAL: Write COMPLETE headers and COMPLETE words - never truncate or cut off mid-word
- CRITICAL: Include ALL sections above - do not skip any section
- CRITICAL: Write professional, detailed content for international use"""
        
        return streaming_system_message, streaming_prompt

    def _determine_schema_type(
        self,
        template_category: TemplateCategory,
        prompt_definition: Dict[str, Any]
    ) -> str:
        """Determine the schema type based on template category."""
        if template_category == TemplateCategory.ASSESSMENT:
            return "assessment_output"
        elif template_category == TemplateCategory.COMMUNICATION:
            return "communication_output"
        else:
            return "universal_output"

    def _build_system_message(
        self,
        schema_type: str,
        prompt_definition: Dict[str, Any],
        output_language: str = "English",
        lang_instruction: str = "in English",
        standard: Optional[str] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build system message with TOON instructions and language/standard handling (like Activity).
        
        Includes:
        - Role definition
        - Language instructions
        - Standard instructions
        - TOON format explanation
        - Output schema instructions
        - Template-specific guidance from prompt_definition
        - Detailed content requirements for LESSON_DESIGN
        """
        parts = []
        
        # Role and core instruction - INTERNATIONAL LEVEL QUALITY
        parts.append("You are an expert instructional designer and educational content creator with extensive experience in international education systems, including USA, UK, IB, and other high-level educational frameworks.")
        parts.append("Generate comprehensive, detailed, and professionally structured educational content suitable for international schools, high-performing institutions, and rigorous academic environments.")
        parts.append("Provide extensive detail in all sections - write full sentences, complete explanations, and thorough descriptions.")
        parts.append("Do not use placeholder text or brief summaries - write complete, actionable content.")
        parts.append("")
        parts.append("INTERNATIONAL QUALITY STANDARDS:")
        parts.append("- Content must meet or exceed standards used in top-tier international schools (USA Common Core, UK National Curriculum, IB, Cambridge, etc.)")
        parts.append("- Use research-based pedagogical approaches (Bloom's Taxonomy, Vygotsky's Zone of Proximal Development, constructivist learning, etc.)")
        parts.append("- Ensure cultural sensitivity and inclusivity - content should be appropriate for diverse, international student populations")
        parts.append("- Align with best practices from leading educational institutions worldwide")
        parts.append("- Use precise academic language appropriate for the grade level and subject area")
        parts.append("- Include rigorous assessment criteria that measure deep understanding, not just surface knowledge")
        parts.append("")
        
        # Language instruction (like Activity) - CRITICAL: Must be very explicit
        parts.append(f"LANGUAGE REQUIREMENT: Generate all content {lang_instruction}.")
        parts.append(f"Write EVERYTHING in {output_language}. All content, headings, descriptions, and text must be in {output_language}.")
        parts.append(f"CRITICAL: All output text, including headings, descriptions, steps, and content, must be generated EXCLUSIVELY in {output_language}.")
        parts.append("")
        
        # Standard instruction - INTERNATIONAL CURRICULUM ALIGNMENT
        # NOTE: standard_note is calculated in build_prompt and passed here if needed
        if standard and standard.strip():
            # Check if standard looks valid (basic validation)
            # Common standard formats: CCSS, UK_NATIONAL, IB, etc.
            common_standard_prefixes = ["CCSS", "UK", "IB", "AUSTRALIAN", "CANADIAN", "SINGAPORE", "NEXT_GEN", "CAMBRIDGE", "EDEXCEL", "AQA"]
            standard_upper = standard.upper().strip()
            is_recognized = any(standard_upper.startswith(prefix) for prefix in common_standard_prefixes)
            
            if not is_recognized:
                parts.append(f"EDUCATIONAL STANDARDS: Align content with the standard: {standard}")
                parts.append(f"IMPORTANT: The standard '{standard}' may not be recognized. In the STANDARDS ALIGNED section, include:")
                parts.append(f"  - A note that the standard '{standard}' may not be recognized or validated")
                parts.append(f"  - General educational standards for the subject at the grade level")
                parts.append(f"  - Adapt materials and recommendations as needed based on constraints and available resources")
            else:
                parts.append(f"EDUCATIONAL STANDARDS: Align content with the standard: {standard}")
                parts.append("Include this standard in the STANDARDS ALIGNED section with full details, including:")
                parts.append("  - Specific standard codes and descriptions")
                parts.append("  - How the content addresses each standard")
                parts.append("  - Connections to related standards in the same framework")
                if "CCSS" in standard_upper:
                    parts.append("  - Note: For USA Common Core, ensure alignment with both content standards and practice standards (Mathematical Practices, ELA Anchor Standards)")
                elif "UK" in standard_upper:
                    parts.append("  - Note: For UK National Curriculum, ensure alignment with both subject content and skills progression")
                elif "IB" in standard_upper:
                    parts.append("  - Note: For IB, ensure alignment with IB Learner Profile attributes and Approaches to Learning (ATL) skills")
            parts.append("")
        else:
            # Even without a specific standard, ensure international quality
            parts.append("EDUCATIONAL STANDARDS: Ensure content aligns with international best practices:")
            parts.append("  - For USA: Consider Common Core State Standards (CCSS) alignment")
            parts.append("  - For UK: Consider National Curriculum and GCSE/A-Level requirements")
            parts.append("  - For International: Consider IB, Cambridge, or other relevant frameworks")
            parts.append("  - Include rigorous, age-appropriate learning objectives")
            parts.append("  - Ensure content promotes critical thinking, problem-solving, and analytical skills")
            parts.append("")
        
        # TOON format explanation
        parts.append("IMPORTANT: Use TOON (Token-Optimized Object Notation) format for your response.")
        parts.append("TOON is a compact format that reduces token usage by ~70% compared to JSON.")
        parts.append("Format: {key:value,key2:value2} for objects, [item1,item2] for arrays.")
        parts.append("Strings without spaces don't need quotes. Use quotes for strings with spaces or special chars.")
        parts.append("")
        
        # Template-specific description from prompt_definition
        if prompt_definition:
            description = prompt_definition.get("description", "")
            if description:
                parts.append(f"Task: {description}")
                parts.append("")
        
        # When template provides output_schema, use ONLY that structure (future-proof, per-template).
        # Do NOT add generic lesson-plan sections (Learning Goals, Opening, Guided Practice, etc.).
        if output_schema and isinstance(output_schema, dict):
            parts.append("Your response must contain ONLY the keys defined in the OUTPUT STRUCTURE below. Use the exact property names from the schema.")
            parts.append("QUALITY: Generate high-quality, international-level content suitable for top-tier institutions (Silicon Valley / global tech and education standards). Every schema key must have substantial, detailed content—no empty sections, no placeholder text, no one-line answers. Write comprehensive, professional material that is ready for expert educators and high-performing schools.")
            parts.append("Do not add sections (e.g. Learning Objective, Opening, Guided Practice) that are not in the schema. Do not leave any key empty.")
            parts.append("")
        # Add detailed content instructions only when no template-specific output_schema (legacy/default)
        elif schema_type == "lesson_design_output" or schema_type == "universal_output":
            parts.append("CONTENT REQUIREMENTS FOR LESSON PLANS (INTERNATIONAL STANDARDS):")
            parts.append("- Overview: Write 2-3 detailed paragraphs explaining the lesson context, purpose, pedagogical approach, and how it fits into broader learning progression.")
            parts.append("- Learning Goals: Provide 3-5 comprehensive, measurable learning objectives using Bloom's Taxonomy levels. Each objective should:")
            parts.append("  * Be specific, measurable, achievable, relevant, and time-bound (SMART)")
            parts.append("  * Clearly state what students will know, understand, and be able to do")
            parts.append("  * Include both content knowledge and skills development")
            parts.append("  * Align with international curriculum standards where applicable")
            parts.append("- Materials: List all required materials with specific details, quantities, and any safety considerations. Include:")
            parts.append("  * Primary materials needed for the lesson")
            parts.append("  * Optional extension materials for advanced learners")
            parts.append("  * Alternative materials for resource-constrained environments")
            parts.append("- Steps: Write detailed step-by-step instructions with precise time allocations, teacher actions, student activities, and formative assessment checkpoints.")
            parts.append("- Lesson Sections: For each section (opening, introduction, guided_practice, independent_practice, closing), provide:")
            parts.append("  * Detailed goals explaining the section's purpose and pedagogical rationale")
            parts.append("  * Multiple steps (4-6 per section) with specific labels, durations, and comprehensive details")
            parts.append("  * Each step detail should be 2-3 sentences explaining what the teacher does, what students do, and why this approach is effective")
            parts.append("  * Include questioning strategies, differentiation opportunities, and assessment moments")
            parts.append("- Assessment: Provide detailed assessment criteria including:")
            parts.append("  * Formative assessment strategies (exit tickets, think-pair-share, quick checks)")
            parts.append("  * Summative assessment options with clear rubrics")
            parts.append("  * Self-assessment and peer-assessment opportunities")
            parts.append("  * Criteria that measure deep understanding, not just memorization")
            parts.append("- Differentiation: Include specific, research-based strategies for:")
            parts.append("  * Struggling learners (scaffolding, additional support, modified tasks)")
            parts.append("  * Advanced learners (extension activities, deeper inquiry, independent projects)")
            parts.append("  * English Language Learners (language support, visual aids, vocabulary pre-teaching)")
            parts.append("  * Students with diverse learning styles (visual, auditory, kinesthetic, reading/writing)")
            parts.append("  * Cultural considerations for international classrooms")
            parts.append("- Teacher Notes: Include pedagogical tips, common misconceptions, safety considerations, and extension ideas.")
            parts.append("")
            parts.append("QUALITY STANDARDS:")
            parts.append("- Write all content in complete, professional sentences using precise academic language.")
            parts.append("- Avoid bullet points without context - provide full explanations.")
            parts.append("- Each section should be comprehensive, research-based, and ready for classroom implementation.")
            parts.append("- Ensure content is culturally sensitive and appropriate for diverse, international student populations.")
            parts.append("- Use evidence-based teaching strategies (active learning, inquiry-based learning, collaborative learning, etc.)")
            parts.append("- Include opportunities for critical thinking, problem-solving, creativity, and metacognition.")
            parts.append("")
        
        # Output schema instructions: use version's output_schema when provided (per-template flexibility)
        if output_schema and isinstance(output_schema, dict):
            parts.append("OUTPUT STRUCTURE (your response must match this schema):")
            parts.append(json.dumps(output_schema, indent=2))
            parts.append("")
            parts.append("IMPORTANT: Return ONLY the data object (the key-value content that fits the schema). Do NOT wrap it in a schema envelope (no top-level 'type', 'required', or 'properties' wrapper). For example, return {\"title\": \"...\", \"overview\": \"...\", ...} not {\"type\": \"object\", \"properties\": {...}}.")
            parts.append("")
        else:
            schema_instruction = self.toon_handler.build_toon_schema_string(schema_type)
            parts.append(schema_instruction)
            parts.append("")
        
        # Additional instructions - INTERNATIONAL QUALITY
        parts.append("Ensure your response is complete, accurate, and follows the TOON schema structure above.")
        parts.append("Return only the TOON-formatted data, no additional explanation.")
        parts.append("")
        parts.append("FINAL QUALITY REQUIREMENTS:")
        parts.append("- Generate detailed, comprehensive content suitable for international schools and high-performing institutions (Silicon Valley / global high-tech education standards).")
        parts.append("- Write full descriptions, complete explanations, and thorough details - no brief summaries, no placeholder text, no empty sections.")
        parts.append("- Every output key in the schema must have substantial content - never leave a section empty or one sentence only.")
        parts.append("- Ensure content is academically rigorous, pedagogically sound, and culturally appropriate.")
        parts.append("- Use research-based teaching methods and align with international best practices.")
        parts.append("- Content should be ready for immediate use in USA, UK, IB, or other high-level international school contexts.")
        parts.append("- Maintain professional tone and precision throughout - this content will be used by expert educators.")
        parts.append("- Include opportunities for student agency, inquiry, and authentic learning experiences.")
        
        return "\n".join(parts)

    def _build_user_prompt(
        self,
        toon_input: str,
        schema_type: str,
        prompt_definition: Dict[str, Any],
        input_data: Dict[str, Any],
        output_language: str = "English",
        lang_instruction: str = "in English",
        language_note: str = "",
        standard: Optional[str] = None,
        standard_note: str = "",
        topic: Optional[str] = None,
        subject: Optional[str] = None,
        grade_band: Optional[str] = None,
        available_time: Optional[int] = None,
        materials: Optional[str] = None,
        constraints: Optional[str] = None
    ) -> str:
        """
        Build user prompt with TOON input and detailed output instructions (like Activity).
        
        Includes:
        - TOON-formatted input data
        - Detailed structure instructions for LESSON_DESIGN
        - Reminder about output format
        - Any additional context from prompt_definition
        """
        parts = []
        
        # Introduction
        parts.append("Generate educational content based on the following input parameters (in TOON format):")
        parts.append("")
        
        # TOON input data
        parts.append(toon_input)
        parts.append("")
        
        # Extract assessment-specific inputs
        question_types = input_data.get("question_types", [])
        difficulty = input_data.get("difficulty", "mixed")
        num_questions = input_data.get("num_questions")
        time_allocation = input_data.get("time_allocation_minutes")
        
        # For ASSESSMENT category, add assessment-specific structure instructions
        if schema_type == "assessment_output":
            parts.append("OUTPUT: Generate a comprehensive summative assessment/test following this EXACT structure and format:")
            parts.append("")
            
            if topic:
                parts.append(f"# [Assessment Title: {topic} - {subject or 'Subject'} Assessment]")
            parts.append("")
            parts.append("## TEST OVERVIEW")
            parts.append(f"[Provide a clear overview of this assessment covering {topic}. Specify the total number of questions, time allocation ({time_allocation or 'appropriate'} minutes), and assessment purpose. Explain how this assessment aligns with the learning objective and measures student understanding at the {difficulty} difficulty level.]")
            parts.append("")
            parts.append("## QUESTIONS BY TYPE")
            if question_types:
                question_types_str = ", ".join(question_types) if isinstance(question_types, list) else str(question_types)
                parts.append(f"[Generate {num_questions or 'an appropriate number of'} questions of the following types: {question_types_str}. Ensure questions are at the {difficulty} difficulty level and assess deep understanding, not just recall.]")
                parts.append("")
                if "MCQ" in question_types or "mcq" in str(question_types).lower():
                    parts.append("### Multiple Choice Questions (MCQ)")
                    parts.append("[Generate 5-10 multiple choice questions. Each question should:")
                    parts.append("  - Have 4 plausible answer options (A, B, C, D)")
                    parts.append("  - Include one clearly correct answer")
                    parts.append("  - Include distractors that reflect common misconceptions")
                    parts.append("  - Assess understanding at the specified Bloom's level")
                    parts.append("  - Be appropriate for the difficulty level specified]")
                    parts.append("")
                if "short_answer" in question_types or "short" in str(question_types).lower():
                    parts.append("### Short Answer Questions")
                    parts.append("[Generate 3-5 short answer questions. Each question should:")
                    parts.append("  - Require 2-3 sentence responses")
                    parts.append("  - Assess specific knowledge and understanding")
                    parts.append("  - Have clear, specific answer criteria")
                    parts.append("  - Be appropriate for the difficulty level specified]")
                    parts.append("")
                if "essay" in question_types:
                    parts.append("### Essay Questions")
                    parts.append("[Generate 1-2 essay questions. Each question should:")
                    parts.append("  - Require extended written responses (1-2 pages)")
                    parts.append("  - Assess analysis, synthesis, and evaluation skills")
                    parts.append("  - Include clear prompts and expectations")
                    parts.append("  - Be appropriate for the difficulty level specified]")
                    parts.append("")
                if "diagram" in question_types:
                    parts.append("### Diagram/Labeling Questions")
                    parts.append("[Generate 2-3 diagram or labeling questions. Each question should:")
                    parts.append("  - Require students to create or label diagrams")
                    parts.append("  - Assess visual-spatial understanding")
                    parts.append("  - Include clear instructions and criteria]")
                    parts.append("")
                if "matching" in question_types:
                    parts.append("### Matching Questions")
                    parts.append("[Generate 1-2 matching questions. Each question should:")
                    parts.append("  - Require pairing related concepts or items")
                    parts.append("  - Have clear instructions")
                    parts.append("  - Include appropriate number of items to match]")
                    parts.append("")
            else:
                parts.append("[Generate questions based on the specified question types. Ensure questions are academically rigorous and assess deep understanding.]")
            parts.append("")
            parts.append("## RUBRIC / MARKING GUIDE")
            parts.append("[Provide a detailed marking rubric that:")
            parts.append("  - Clearly distinguishes between performance levels (e.g., Excellent, Good, Satisfactory, Needs Improvement)")
            parts.append("  - Specifies point allocation for each question or section")
            parts.append("  - Includes criteria for partial credit where applicable")
            parts.append("  - Aligns with the difficulty level and Bloom's taxonomy levels")
            parts.append("  - Provides clear descriptors for each performance level]")
            parts.append("")
            parts.append("## ANSWER KEY")
            parts.append("[Provide a comprehensive answer key that includes:")
            parts.append("  - Correct answers for all questions")
            parts.append("  - Detailed explanations for why answers are correct")
            parts.append("  - Common misconceptions and why they are incorrect (for MCQ distractors)")
            parts.append("  - Sample responses for open-ended questions (short answer, essay)")
            parts.append("  - Point allocation for each question]")
            parts.append("")
            parts.append("## BLOOM'S TAXONOMY CATEGORIZATION")
            parts.append("[Categorize each question by Bloom's Taxonomy level and explain how it assesses that cognitive level. Ensure the assessment covers the specified Bloom's level(s) and difficulty.]")
            parts.append("")
            parts.append("## STANDARDS ALIGNMENT")
            standard_text = f" that align with: {standard}" if standard and standard.strip() else ""
            parts.append(f"[List applicable educational standards for {subject or 'Subject'} at {grade_band or 'Grade'} level{standard_text}. Explain how this assessment measures student achievement of these standards.]")
            parts.append("")
            if time_allocation:
                parts.append(f"IMPORTANT: Ensure the assessment can be completed within {time_allocation} minutes. Adjust question complexity and number accordingly.")
            if difficulty == "hard":
                parts.append("CRITICAL: This assessment is at HARD difficulty level. Questions must require:")
                parts.append("  - Advanced critical thinking and problem-solving")
                parts.append("  - Evaluation and synthesis skills")
                parts.append("  - Complex application of concepts")
                parts.append("  - Multi-step reasoning")
            parts.append("")
        
        # For LESSON_DESIGN category, add detailed structure instructions (like Activity streaming prompt)
        elif schema_type == "lesson_design_output" or schema_type == "universal_output":
            parts.append("OUTPUT: Generate a detailed lesson plan following this EXACT structure and format:")
            parts.append("")
            
            if topic:
                parts.append(f"# [Lesson Title: {topic}]")
            parts.append("")
            parts.append("## LEARNING OBJECTIVE")
            parts.append("[Write a clear, measurable learning objective. Students will...]")
            parts.append("")
            parts.append("## ASSESSMENT")
            parts.append("[Describe how students will demonstrate mastery. Include: working prototype/demonstration, written explanation, rubric-based assessment covering reliability, component interaction, and justification of choices/safety considerations.]")
            parts.append("")
            parts.append("## KEY POINTS")
            parts.append("- [Core concept 1: e.g., Fundamentals related to the topic]")
            parts.append("- [Core concept 2: e.g., Practical application and hands-on learning]")
            parts.append("- [Core concept 3: e.g., Design process and documentation]")
            parts.append("- [Core concept 4: e.g., Safety and classroom management]")
            parts.append("- [Core concept 5: Add more as appropriate for the topic]")
            parts.append("")
            parts.append("## OPENING")
            parts.append("- **Hook (1-2 minutes)**: [Brief video/demo or engaging introduction]")
            parts.append("- **Goal Explanation**: [Explain the lesson's goal and what students will accomplish]")
            parts.append("- **Group Organization**: [Organize students into groups with assigned roles]")
            parts.append("- **Anticipatory Question**: [Pose a question to engage students]")
            parts.append("")
            parts.append("## INTRODUCTION TO NEW MATERIAL")
            parts.append("[5-8 minutes per mini-topic]")
            parts.append(f"- **Key Concepts**: [Explain main concepts related to {topic or 'the topic'}]")
            if materials:
                parts.append(f"- **Materials Overview**: [Explain how to use: {materials}]")
            parts.append("- **Basic Principles**: [Explain fundamental principles]")
            parts.append("- **Active Learning**: [Include hands-on activity or demonstration]")
            parts.append("- **Common Misconception**: [Address a common misconception about the topic]")
            parts.append("")
            parts.append("## GUIDED PRACTICE")
            parts.append("- **Behavioral Expectations**: [Set clear expectations for student behavior]")
            parts.append("- **Component Identification (5 minutes)**: [Activity to identify key elements]")
            parts.append("- **Simple Activity Build (10 minutes)**: [Step-by-step activity building]")
            parts.append("- **Practice Exercise (10-15 minutes)**: [Guided practice with teacher support and guiding questions]")
            parts.append("- **Task Challenge Introduction (10 minutes)**: [Introduce the main challenge with success criteria and model timeline]")
            parts.append("- **Monitoring**: [Use checklist and probing questions to monitor student performance]")
            parts.append("")
            parts.append("## INDEPENDENT PRACTICE")
            parts.append("- **Behavioral Expectations**: [Set expectations for collaborative work]")
            parts.append("- **Assignment**: [Teams design and complete the main activity]")
            parts.append("- **Deliverables**:")
            parts.append("  - Working prototype or completed work")
            parts.append("  - One-page design explanation")
            parts.append("  - Team demonstration")
            if available_time:
                parts.append(f"- **Timeline**: [Adapt for {available_time} minute lesson or split across two class periods]")
            parts.append("- **Teacher Support**: [Mini-lessons and rubric for formative feedback]")
            parts.append("")
            parts.append("## CLOSING")
            parts.append("- **Exit Activity**: [Quick activity where teams share success/challenge]")
            parts.append("- **Restatement**: [Restate learning objective and assessment criteria]")
            parts.append("")
            parts.append("## EXTENSION ACTIVITY")
            parts.append("[For early finishers: Add a secondary objective or challenge with documentation and testing]")
            parts.append("")
            parts.append("## HOMEWORK")
            parts.append("[Individual reflection/journal on activity behavior, technical challenges, and potential improvements with additional resources]")
            parts.append("")
            parts.append("## STANDARDS ALIGNED")
            standard_text = f" that align with: {standard}" if standard and standard.strip() else ""
            parts.append(f"- **Relevant Standards**: [List applicable educational standards for {subject or 'Subject'} at {grade_band or 'Grade'} level{standard_text}]")
            constraints_text = constraints or "None specified"
            parts.append(f"- **Note**: [Adapt materials and recommendations as needed based on: {constraints_text}]")
            parts.append("")
            # CRITICAL: Language instruction must be VERY explicit and repeated (like Activity)
            parts.append(f"OUTPUT LANGUAGE: Write EVERYTHING {lang_instruction}.")
            parts.append(f"REMEMBER: Write EVERYTHING in {output_language}. All content, headings, and text must be in {output_language}.")
            parts.append(f"Generate all text, headings, descriptions, and content EXCLUSIVELY in {output_language}.")
            parts.append(f"CRITICAL INSTRUCTION: Every single word, heading, description, step, and piece of content MUST be written in {output_language}.")
            parts.append(f"DO NOT use any other language. Write ONLY in {output_language}.")
            if language_note:
                parts.append(language_note)
            if materials:
                parts.append(f"Use the EXACT materials specified: {materials}.")
            if constraints:
                parts.append(f"Consider these constraints: {constraints}.")
            if grade_band and available_time:
                parts.append(f"Make it appropriate for {grade_band} grade level and {available_time} minutes duration.")
            if standard and standard.strip():
                parts.append(f"IMPORTANT: Align content with the educational standard: {standard}")
                if standard_note:
                    parts.append(standard_note)
                else:
                    parts.append(f"Include the standard '{standard}' in the STANDARDS ALIGNED section with full details.")
            parts.append("")
        
        # Output format reminder
        parts.append("Provide your response in TOON format matching the schema provided in the system message.")
        
        # Additional context from prompt_definition if available
        if prompt_definition:
            context = prompt_definition.get("context")
            if context:
                parts.append("")
                parts.append(f"Additional context: {context}")
        
        return "\n".join(parts)

