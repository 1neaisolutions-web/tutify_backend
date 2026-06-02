"""Tests for language list API and BCP 47 validation."""
import pytest
from fastapi.testclient import TestClient

from app.domains.auth.language_data import WORLD_LANGUAGES
from app.domains.auth.language_validation import is_valid_language_tag


def test_is_valid_language_tag_accepts_bcp47():
    assert is_valid_language_tag("en-US") is True
    assert is_valid_language_tag("es-ES") is True
    assert is_valid_language_tag("zh-Hant-TW") is True


def test_is_valid_language_tag_rejects_invalid():
    assert is_valid_language_tag("") is False
    assert is_valid_language_tag("invalid tag") is False
    assert is_valid_language_tag("x") is False


def test_world_languages_non_empty():
    assert len(WORLD_LANGUAGES) > 50
    assert WORLD_LANGUAGES[0]["code"] == "en-US"
    assert "nativeName" in WORLD_LANGUAGES[0]


def test_list_languages_endpoint(client: TestClient):
    response = client.get("/api/v1/languages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == len(WORLD_LANGUAGES)
    assert data[0]["code"] == "en-US"
