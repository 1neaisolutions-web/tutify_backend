"""
TOON (Token-Optimized Object Notation) handler for LLM communication.

Handles encoding/decoding of data to/from TOON format for token efficiency.
"""
import json
from typing import Any, Dict, Optional

from app.core.logging import get_logger

from utils.toon_utils import json_to_toon, toon_to_json

logger = get_logger(__name__)


class TOONHandler:
    """Handles TOON format encoding/decoding for LLM communication."""

    def encode_input(self, data: Dict[str, Any]) -> str:
        """
        Convert input data to TOON format for token efficiency.
        
        Wraps utils/toon_utils.py json_to_toon() function.
        
        Args:
            data: Input data dictionary
        
        Returns:
            TOON-formatted string
        """
        try:
            return json_to_toon(data)
        except Exception as e:
            logger.error(f"Failed to encode input to TOON: {e}")
            # Fallback to JSON string
            return json.dumps(data, separators=(',', ':'))

    def parse_output(
        self,
        toon_string: str,
        schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse TOON response from LLM.
        
        - Cleans markdown code fences if present
        - Parses TOON to JSON dict
        - Falls back to JSON parsing if TOON fails
        - Validates against schema if provided
        
        Args:
            toon_string: TOON-formatted string from LLM
            schema: Optional schema string for validation
        
        Returns:
            Parsed dictionary
        
        Raises:
            ValueError: If parsing fails and no fallback works
        """
        # Clean markdown code fences
        cleaned = self._clean_markdown_fences(toon_string)
        
        try:
            # Try TOON parsing first
            parsed = toon_to_json(cleaned)
            
            # Validate against schema if provided
            if schema:
                if not self.validate_schema(parsed, schema):
                    logger.warning("Parsed data does not match schema, but continuing")
            
            return parsed
            
        except (ValueError, Exception) as e:
            logger.warning(f"TOON parsing failed: {e}, attempting JSON fallback")
            
            # Fallback to JSON parsing
            try:
                # Try to extract JSON from markdown if present
                json_str = cleaned
                if "```json" in json_str:
                    start = json_str.find("```json") + 7
                    end = json_str.find("```", start)
                    json_str = json_str[start:end].strip()
                elif "```" in json_str:
                    start = json_str.find("```") + 3
                    end = json_str.find("```", start)
                    json_str = json_str[start:end].strip()
                
                parsed = json.loads(json_str)
                
                # Validate against schema if provided
                if schema:
                    if not self.validate_schema(parsed, schema):
                        logger.warning("JSON fallback does not match schema, but continuing")
                
                return parsed
                
            except json.JSONDecodeError as json_err:
                logger.error(f"Both TOON and JSON parsing failed: {json_err}")
                raise ValueError(f"Failed to parse response: TOON error: {e}, JSON error: {json_err}")

    def _clean_markdown_fences(self, text: str) -> str:
        """Remove markdown code fences if present."""
        text = text.strip()
        
        # Remove ```toon or ```json at start
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        return text.strip()

    def validate_schema(
        self,
        data: Dict[str, Any],
        schema: str
    ) -> bool:
        """
        Validate parsed data against TOON schema.
        
        This is a basic validation - checks for required top-level keys.
        More sophisticated validation can be added later.
        
        Args:
            data: Parsed data dictionary
            schema: Schema string (can be TOON format or JSON schema description)
        
        Returns:
            True if data appears to match schema, False otherwise
        """
        try:
            # Try to parse schema as TOON or JSON
            if schema.strip().startswith(("{", "[")):
                schema_dict = toon_to_json(schema) if ":" in schema or not schema.strip().startswith("{") else json.loads(schema)
            else:
                # Assume it's a description or list of required keys
                # For now, just check if it mentions required fields
                return True  # Basic validation - always pass for now
            
            # If schema is a dict with "required" key, validate
            if isinstance(schema_dict, dict) and "required" in schema_dict:
                required = schema_dict["required"]
                if isinstance(required, list):
                    for key in required:
                        if key not in data:
                            logger.warning(f"Required key '{key}' missing from data")
                            return False
            
            # If schema is a dict with "properties", check structure
            if isinstance(schema_dict, dict) and "properties" in schema_dict:
                properties = schema_dict["properties"]
                if isinstance(properties, dict):
                    # Basic check: ensure data keys match expected properties
                    # This is lenient - just checks structure exists
                    pass
            
            return True
            
        except Exception as e:
            logger.warning(f"Schema validation error: {e}, assuming valid")
            return True  # Fail open for now

    def build_toon_schema_string(
        self,
        schema_type: str,
        num_variants: int = 1
    ) -> str:
        """
        Build TOON schema string for prompt instructions.
        
        Args:
            schema_type: Type of schema (e.g., "universal_output", "assessment_output", "communication_output")
            num_variants: Number of example variants to include
        
        Returns:
            TOON schema string with structure description
        """
        # Base universal output schema
        base_schema = {
            "overview": "string",
            "learning_goals": ["string"],
            "materials": ["string"],
            "steps": [{"title": "string", "description": "string"}],
            "differentiation": ["string"],
            "assessment": {
                "checks_for_understanding": ["string"],
                "rubric": "optional string"
            },
            "teacher_notes": ["string"],
            "bloom_alignment": [{"level": "string", "description": "string"}]
        }
        
        if schema_type == "assessment_output":
            base_schema["questions"] = [
                {
                    "question_text": "string",
                    "type": "string",
                    "answer_key": "optional string",
                    "difficulty": "optional string"
                }
            ]
        
        elif schema_type == "communication_output":
            base_schema["communication"] = {
                "subject_line": "string",
                "message_body": "string",
                "key_details": ["string"],
                "call_to_action": "string"
            }
        
        # Convert to TOON format
        schema_toon = json_to_toon(base_schema)
        
        # Build instruction string
        instruction = f"Output format (TOON):\n{schema_toon}\n\n"
        instruction += "Use TOON format for compact token usage. Example structure above."
        
        if num_variants > 1:
            instruction += f"\nProvide {num_variants} variant(s) if applicable."
        
        return instruction

