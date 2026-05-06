"""
Model adapter for PixGen image generation providers.

This module intentionally isolates provider-specific logic so we can
swap OpenAI for another image provider later without changing route/service code.
"""
from typing import Any, Dict

from openai import OpenAI

from app.core.logging import get_logger
from app.llm.config import llm_settings

logger = get_logger(__name__)

ASPECT_RATIO_TO_SIZE = {
    "1:1 Square": "1024x1024",
    "3:2 Landscape": "1536x1024",
    "9:16 Vertical": "1024x1536",
    "2:3 Portrait": "1024x1536",
}

DALL_E_2_FALLBACK_SIZE = "1024x1024"
DALL_E_3_SIZE_MAP = {
    "1:1 Square": "1024x1024",
    "3:2 Landscape": "1792x1024",
    "9:16 Vertical": "1024x1792",
    "2:3 Portrait": "1024x1792",
}


def _build_provider_prompt(prompt: str, style_preset: str, aspect_ratio: str) -> str:
    """Compose a model-friendly prompt for consistent style and framing."""
    return (
        f"{prompt}\n\n"
        f"Style preset: {style_preset}\n"
        f"Aspect ratio target: {aspect_ratio}\n"
        "Output should be classroom-safe and suitable for educational use."
    )


def _resolve_size_for_model(model_name: str, aspect_ratio: str) -> str:
    """
    Resolve an image size compatible with the selected OpenAI image model.
    """
    normalized = model_name.lower()
    if "dall-e-2" in normalized:
        return DALL_E_2_FALLBACK_SIZE
    if "dall-e-3" in normalized:
        return DALL_E_3_SIZE_MAP.get(aspect_ratio, "1024x1024")
    return ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "1024x1024")


def generate_image_with_model(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an image using OpenAI image API and return normalized output.

    Returns a provider-agnostic dict consumed by PixGenService.
    """
    if getattr(llm_settings, "OPENAI_EMBEDDINGS_ONLY_MODE", False):
        raise ValueError(
            "PixGen OpenAI usage is disabled (OPENAI_EMBEDDINGS_ONLY_MODE=true)."
        )
    if not getattr(llm_settings, "LLM_OUTBOUND_ENABLED", True):
        raise ValueError(
            "Image generation is disabled because LLM_OUTBOUND_ENABLED=false. "
            "Set LLM_OUTBOUND_ENABLED=true when you intentionally want to call OpenAI images."
        )
    if not llm_settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    prompt = params["prompt"]
    style_preset = params["stylePreset"]
    aspect_ratio = params["aspectRatio"]
    model_name = params.get("model") or llm_settings.OPENAI_IMAGE_MODEL
    size = _resolve_size_for_model(model_name=model_name, aspect_ratio=aspect_ratio)

    client = OpenAI(api_key=llm_settings.OPENAI_API_KEY, base_url=llm_settings.OPENAI_BASE_URL)
    provider_prompt = _build_provider_prompt(prompt=prompt, style_preset=style_preset, aspect_ratio=aspect_ratio)

    response = client.images.generate(
        model=model_name,
        prompt=provider_prompt,
        size=size,
    )

    image_url = None
    if getattr(response, "data", None):
        first_item = response.data[0]
        if getattr(first_item, "url", None):
            image_url = first_item.url
        elif getattr(first_item, "b64_json", None):
            # Return a browser-friendly data URL so frontend can render immediately.
            image_url = f"data:image/png;base64,{first_item.b64_json}"

    if not image_url:
        raise ValueError("OpenAI image generation returned no image payload.")

    return {
        "imageUrl": image_url,
        "status": "completed",
        "provider": "openai",
        "model": model_name,
        "metadata": {
            "size": size,
        },
    }
