"""
TOON (Token-Optimized Object Notation) utilities for encoding/decoding.

TOON is a compact format that reduces token usage by ~70% compared to JSON
while maintaining readability and structure.
"""
import json
import re
from typing import Any, Dict, List, Optional, Union


def json_to_toon(data: Union[Dict[str, Any], List[Any]], indent: int = 0) -> str:
    """
    Convert JSON-compatible data structure to TOON format.
    
    TOON format rules:
    - Objects: {key:value,key2:value2}
    - Arrays: [item1,item2,item3]
    - Strings: "string" or 'string' (no quotes if no spaces/special chars)
    - Numbers: 123, 45.67
    - Booleans: true, false
    - Null: null
    - Nested structures use minimal whitespace
    
    Args:
        data: JSON-compatible dict or list
        indent: Current indentation level (for pretty printing, not used in compact mode)
    
    Returns:
        TOON-formatted string
    """
    if isinstance(data, dict):
        if not data:
            return "{}"
        
        parts = []
        for key, value in data.items():
            # Key: always quote if contains special chars or spaces
            key_str = _quote_if_needed(str(key))
            value_str = json_to_toon(value, indent + 1)
            parts.append(f"{key_str}:{value_str}")
        
        return "{" + ",".join(parts) + "}"
    
    elif isinstance(data, list):
        if not data:
            return "[]"
        
        parts = [json_to_toon(item, indent + 1) for item in data]
        return "[" + ",".join(parts) + "]"
    
    elif isinstance(data, str):
        return _quote_if_needed(data)
    
    elif isinstance(data, (int, float)):
        return str(data)
    
    elif isinstance(data, bool):
        return "true" if data else "false"
    
    elif data is None:
        return "null"
    
    else:
        # Fallback: convert to string and quote
        return _quote_if_needed(str(data))


def _quote_if_needed(s: str) -> str:
    """Quote string only if it contains spaces, special chars, or is empty."""
    if not s:
        return '""'
    
    # Check if string needs quoting
    needs_quotes = (
        " " in s or
        "\n" in s or
        "\t" in s or
        s[0].isdigit() or
        any(char in s for char in ":{}[],\"'")
    )
    
    if needs_quotes:
        # Escape quotes and wrap
        escaped = s.replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
        return f'"{escaped}"'
    else:
        return s


def toon_to_json(toon_string: str) -> Dict[str, Any]:
    """
    Parse TOON string back to JSON-compatible dict/list.
    
    Args:
        toon_string: TOON-formatted string
    
    Returns:
        Parsed JSON-compatible structure (dict or list)
    
    Raises:
        ValueError: If TOON string cannot be parsed
    """
    # Clean the string first
    toon_string = toon_string.strip()
    
    # Remove markdown code fences if present
    toon_string = _clean_markdown_fences(toon_string)
    
    try:
        return _parse_toon_value(toon_string.strip())
    except Exception as e:
        raise ValueError(f"Failed to parse TOON: {e}")


def _clean_markdown_fences(text: str) -> str:
    """Remove markdown code fences (```toon, ```json, ```) if present."""
    # Remove ```toon or ```json at start
    text = re.sub(r'^```(?:toon|json)?\s*\n?', '', text, flags=re.MULTILINE)
    # Remove ``` at end
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    return text.strip()


def _parse_toon_value(s: str) -> Any:
    """Parse a TOON value (recursive)."""
    s = s.strip()
    
    if not s:
        raise ValueError("Empty TOON value")
    
    # Object: {key:value,...}
    if s.startswith("{") and s.endswith("}"):
        return _parse_toon_object(s[1:-1])
    
    # Array: [value,...]
    elif s.startswith("[") and s.endswith("]"):
        return _parse_toon_array(s[1:-1])
    
    # String: "..." or '...'
    elif (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return _parse_toon_string(s)
    
    # Number
    elif s.replace('.', '', 1).replace('-', '', 1).isdigit():
        try:
            if '.' in s:
                return float(s)
            else:
                return int(s)
        except ValueError:
            return s
    
    # Boolean
    elif s.lower() == "true":
        return True
    elif s.lower() == "false":
        return False
    
    # Null
    elif s.lower() == "null":
        return None
    
    # Unquoted string (no spaces, no special chars)
    else:
        return s


def _parse_toon_object(content: str) -> Dict[str, Any]:
    """Parse TOON object content: key:value,key2:value2"""
    if not content.strip():
        return {}
    
    result = {}
    depth = 0
    in_string = False
    string_char = None
    current_key = ""
    current_value = ""
    i = 0
    
    while i < len(content):
        char = content[i]
        
        # Track string boundaries
        if char in ('"', "'") and (i == 0 or content[i-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
        
        # Track depth for nested structures
        if not in_string:
            if char in ('{', '['):
                depth += 1
            elif char in ('}', ']'):
                depth -= 1
        
        # Key-value separator (only at depth 0)
        if char == ':' and depth == 0 and not in_string:
            current_key = content[:i].strip()
            # Find the end of this value
            value_start = i + 1
            value_end = _find_value_end(content, value_start)
            current_value = content[value_start:value_end].strip()
            
            # Parse key and value
            key = _parse_toon_string(current_key) if current_key.startswith(('"', "'")) else current_key.strip('"\'')
            value = _parse_toon_value(current_value)
            result[key] = value
            
            # Move past this key-value pair and comma
            i = value_end
            if i < len(content) and content[i] == ',':
                i += 1
            content = content[i:].strip()
            i = 0
            continue
        
        i += 1
    
    # Handle last key-value if no trailing comma
    if current_key and not result:
        # Simple case: single key-value
        if ':' in content:
            parts = content.split(':', 1)
            key = _parse_toon_string(parts[0].strip()) if parts[0].strip().startswith(('"', "'")) else parts[0].strip().strip('"\'')
            value = _parse_toon_value(parts[1].strip())
            result[key] = value
    
    return result


def _find_value_end(content: str, start: int) -> int:
    """Find the end of a TOON value (handles nested structures)."""
    depth = 0
    in_string = False
    string_char = None
    i = start
    
    while i < len(content):
        char = content[i]
        
        if char in ('"', "'") and (i == 0 or content[i-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
        
        if not in_string:
            if char in ('{', '['):
                depth += 1
            elif char in ('}', ']'):
                depth -= 1
                if depth < 0:
                    return i
            elif char == ',' and depth == 0:
                return i
        
        i += 1
    
    return len(content)


def _parse_toon_array(content: str) -> List[Any]:
    """Parse TOON array content: value1,value2,value3"""
    if not content.strip():
        return []
    
    result = []
    depth = 0
    in_string = False
    string_char = None
    current_value = ""
    i = 0
    start = 0
    
    while i < len(content):
        char = content[i]
        
        if char in ('"', "'") and (i == 0 or content[i-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
        
        if not in_string:
            if char in ('{', '['):
                depth += 1
            elif char in ('}', ']'):
                depth -= 1
            elif char == ',' and depth == 0:
                # End of current value
                value_str = content[start:i].strip()
                if value_str:
                    result.append(_parse_toon_value(value_str))
                start = i + 1
        
        i += 1
    
    # Last value
    if start < len(content):
        value_str = content[start:].strip()
        if value_str:
            result.append(_parse_toon_value(value_str))
    
    return result


def _parse_toon_string(s: str) -> str:
    """Parse a TOON string (with quotes)."""
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
        # Unescape
        s = s.replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n').replace('\\t', '\t')
    return s

