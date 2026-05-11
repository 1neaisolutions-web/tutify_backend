"""
Unit tests for PixGenService in app/domains/pixgen/services/pixgen_service.py.
Model adapter and DB are mocked.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.domains.pixgen.schemas import GenerateImageRequest, GenerateBatchRequest
from app.domains.pixgen.services.pixgen_service import PixGenService
from app.domains.pixgen.models import PixGenGeneration


def _make_db():
    db = MagicMock()
    return db


def _make_generation(**kwargs):
    gen = MagicMock(spec=PixGenGeneration)
    gen.id = uuid.uuid4()
    gen.user_id = uuid.uuid4()
    gen.prompt = kwargs.get("prompt", "a sunset")
    gen.image_url = kwargs.get("image_url", "https://cdn.example.com/img.png")
    gen.status = kwargs.get("status", "completed")
    gen.style_preset = kwargs.get("style_preset", "photographic")
    gen.aspect_ratio = kwargs.get("aspect_ratio", "1:1")
    gen.provider = kwargs.get("provider", "stability")
    gen.model = kwargs.get("model", "stable-diffusion-xl")
    gen.generation_metadata = kwargs.get("generation_metadata", {})
    gen.error = kwargs.get("error", None)
    gen.created_at = datetime.now(timezone.utc)
    return gen


_MODEL_RESULT = {
    "imageUrl": "https://cdn.example.com/img.png",
    "status": "completed",
    "provider": "stability",
    "model": "sdxl",
    "metadata": {"seed": 42},
}


# ---------------------------------------------------------------------------
# generate_single
# ---------------------------------------------------------------------------

class TestGenerateSingle:
    def _payload(self, prompt="a sunset"):
        return GenerateImageRequest(
            prompt=prompt,
            stylePreset="photographic",
            aspectRatio="1:1",
        )

    def test_successful_generation_returns_response(self):
        db = _make_db()
        gen = _make_generation()
        db.refresh.side_effect = lambda obj: None

        with patch(
            "app.domains.pixgen.services.pixgen_service.PixGenGeneration",
            return_value=gen,
        ), patch(
            "app.domains.pixgen.services.pixgen_service.generate_image_with_model",
            return_value=_MODEL_RESULT,
        ):
            svc = PixGenService(db)
            result = svc.generate_single(gen.user_id, self._payload())

        assert result.id == gen.id
        assert result.status == "completed"
        assert gen.image_url == _MODEL_RESULT["imageUrl"]

    def test_model_failure_sets_failed_status(self):
        db = _make_db()
        gen = _make_generation(status="processing")
        db.refresh.side_effect = lambda obj: None

        with patch(
            "app.domains.pixgen.services.pixgen_service.PixGenGeneration",
            return_value=gen,
        ), patch(
            "app.domains.pixgen.services.pixgen_service.generate_image_with_model",
            side_effect=RuntimeError("model unavailable"),
        ):
            svc = PixGenService(db)
            with pytest.raises(RuntimeError):
                svc.generate_single(gen.user_id, self._payload(), raise_on_error=True)

        assert gen.status == "failed"
        assert "model unavailable" in gen.error

    def test_model_failure_does_not_raise_when_raise_on_error_false(self):
        db = _make_db()
        gen = _make_generation(status="processing")
        db.refresh.side_effect = lambda obj: None

        with patch(
            "app.domains.pixgen.services.pixgen_service.PixGenGeneration",
            return_value=gen,
        ), patch(
            "app.domains.pixgen.services.pixgen_service.generate_image_with_model",
            side_effect=RuntimeError("fail"),
        ):
            svc = PixGenService(db)
            result = svc.generate_single(gen.user_id, self._payload(), raise_on_error=False)

        assert result.status == "failed"

    def test_generation_always_persists_even_on_failure(self):
        db = _make_db()
        gen = _make_generation()
        db.refresh.side_effect = lambda obj: None

        with patch(
            "app.domains.pixgen.services.pixgen_service.PixGenGeneration",
            return_value=gen,
        ), patch(
            "app.domains.pixgen.services.pixgen_service.generate_image_with_model",
            side_effect=RuntimeError("oops"),
        ):
            svc = PixGenService(db)
            try:
                svc.generate_single(gen.user_id, self._payload())
            except RuntimeError:
                pass

        db.commit.assert_called()  # always committed


# ---------------------------------------------------------------------------
# generate_batch
# ---------------------------------------------------------------------------

class TestGenerateBatch:
    def test_batch_generates_correct_count(self):
        db = _make_db()
        payload = GenerateBatchRequest(
            prompt="a mountain",
            stylePreset="photographic",
            aspectRatio="16:9",
            batchSize=3,
        )
        gen = _make_generation()
        db.refresh.side_effect = lambda obj: None

        with patch(
            "app.domains.pixgen.services.pixgen_service.PixGenGeneration",
            return_value=gen,
        ), patch(
            "app.domains.pixgen.services.pixgen_service.generate_image_with_model",
            return_value=_MODEL_RESULT,
        ):
            svc = PixGenService(db)
            results = svc.generate_batch(uuid.uuid4(), payload)

        assert len(results) == 3

    def test_batch_continues_after_single_failure(self):
        db = _make_db()
        payload = GenerateBatchRequest(
            prompt="test",
            stylePreset="photographic",
            aspectRatio="1:1",
            batchSize=3,
        )
        gen = _make_generation()
        db.refresh.side_effect = lambda obj: None
        call_count = [0]

        def model_side_effect(payload):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("transient error")
            return _MODEL_RESULT

        with patch(
            "app.domains.pixgen.services.pixgen_service.PixGenGeneration",
            return_value=gen,
        ), patch(
            "app.domains.pixgen.services.pixgen_service.generate_image_with_model",
            side_effect=model_side_effect,
        ):
            svc = PixGenService(db)
            results = svc.generate_batch(uuid.uuid4(), payload)

        assert len(results) == 3  # batch completes regardless of single failure


# ---------------------------------------------------------------------------
# get_generation_status
# ---------------------------------------------------------------------------

class TestGetGenerationStatus:
    def test_returns_status_for_existing_generation(self):
        gen = _make_generation()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = gen

        svc = PixGenService(db)
        result = svc.get_generation_status(gen.user_id, gen.id)

        assert result is not None
        assert result.id == gen.id
        assert result.status == gen.status

    def test_returns_none_for_missing_generation(self):
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        svc = PixGenService(db)
        result = svc.get_generation_status(uuid.uuid4(), uuid.uuid4())
        assert result is None

    def test_returns_none_for_wrong_user(self):
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None  # filter includes user_id

        svc = PixGenService(db)
        result = svc.get_generation_status(uuid.uuid4(), uuid.uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# list_user_generations
# ---------------------------------------------------------------------------

class TestListUserGenerations:
    def test_returns_list_of_responses(self):
        gens = [_make_generation() for _ in range(3)]
        db = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = gens

        svc = PixGenService(db)
        results = svc.list_user_generations(uuid.uuid4(), limit=10, offset=0)
        assert len(results) == 3

    def test_returns_empty_list_when_no_generations(self):
        db = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        svc = PixGenService(db)
        results = svc.list_user_generations(uuid.uuid4())
        assert results == []
