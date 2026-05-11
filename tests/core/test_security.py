"""
Unit tests for app/core/security.py — pure functions, no DB needed.
"""
import pytest
from datetime import timedelta

from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_token_string,
)
from app.core.exceptions import InvalidTokenError


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_returns_bcrypt_string(self):
        hashed = hash_password("TestPass1!")
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        pw = "MyS3cur3P@ss"
        assert verify_password(pw, hash_password(pw)) is True

    def test_verify_wrong_password(self):
        assert verify_password("wrongpass", hash_password("rightpass123A!")) is False

    def test_hash_is_unique_per_call(self):
        pw = "SamePass1!"
        assert hash_password(pw) != hash_password(pw)  # different salts

    def test_verify_handles_long_password(self):
        long_pw = "A" * 100 + "b1!"
        hashed = hash_password(long_pw)
        assert verify_password(long_pw, hashed) is True


# ---------------------------------------------------------------------------
# Password strength validation
# ---------------------------------------------------------------------------

VALID_PASSWORD = "Secure@Pass1"


class TestPasswordStrength:
    def test_valid_password_passes(self):
        ok, err = validate_password_strength(VALID_PASSWORD)
        assert ok is True
        assert err is None

    def test_too_short_fails(self):
        ok, err = validate_password_strength("Sh0rt!")
        assert ok is False
        assert "characters" in err

    def test_missing_uppercase_fails(self):
        ok, err = validate_password_strength("nouppercase1!")
        assert ok is False
        assert "uppercase" in err

    def test_missing_lowercase_fails(self):
        ok, err = validate_password_strength("NOLOWER123!")
        assert ok is False
        assert "lowercase" in err

    def test_missing_number_fails(self):
        ok, err = validate_password_strength("NoNumbers!!")
        assert ok is False
        assert "number" in err

    def test_missing_special_char_fails(self):
        ok, err = validate_password_strength("NoSpecial1A")
        assert ok is False
        assert "special" in err

    @pytest.mark.parametrize("pw", [
        "Secure@Pass1",
        "MyStr0ng!Pass",
        "C0mpl3x#Word",
    ])
    def test_various_valid_passwords(self, pw):
        ok, _ = validate_password_strength(pw)
        assert ok is True


# ---------------------------------------------------------------------------
# JWT access / refresh tokens
# ---------------------------------------------------------------------------

class TestJWTTokens:
    def test_create_and_decode_access_token(self):
        data = {"user_id": "abc123", "email": "u@test.com"}
        token = create_access_token(data)
        payload = decode_token(token, token_type="access")
        assert payload["user_id"] == "abc123"
        assert payload["email"] == "u@test.com"
        assert payload["type"] == "access"

    def test_access_token_custom_expiry(self):
        token = create_access_token({"user_id": "x"}, expires_delta=timedelta(minutes=5))
        payload = decode_token(token, token_type="access")
        assert payload["user_id"] == "x"

    def test_create_and_decode_refresh_token(self):
        token = create_refresh_token({"user_id": "abc"})
        payload = decode_token(token, token_type="refresh")
        assert payload["user_id"] == "abc"
        assert payload["type"] == "refresh"

    def test_wrong_token_type_raises(self):
        access_token = create_access_token({"user_id": "x"})
        with pytest.raises(InvalidTokenError):
            decode_token(access_token, token_type="refresh")

    def test_tampered_token_raises(self):
        token = create_access_token({"user_id": "x"})
        tampered = token[:-4] + "xxxx"
        with pytest.raises(InvalidTokenError):
            decode_token(tampered)

    def test_expired_token_raises(self):
        token = create_access_token({"user_id": "x"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(InvalidTokenError):
            decode_token(token)


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

class TestGenerateTokenString:
    def test_returns_non_empty_string(self):
        token = generate_token_string()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_tokens_are_unique(self):
        tokens = {generate_token_string() for _ in range(20)}
        assert len(tokens) == 20
