import pytest
from pydantic import ValidationError

from apps.api.app.config import Settings


def test_production_rejects_development_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY must be a unique value"):
        Settings(ENVIRONMENT="production")


def test_production_accepts_long_custom_secret():
    secret = "b9e3d72a51c60f84" * 4
    config = Settings(
        ENVIRONMENT="production",
        SECRET_KEY=secret
    )
    assert config.SECRET_KEY == secret


def test_production_rejects_repeated_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY must be a unique value"):
        Settings(ENVIRONMENT="production", SECRET_KEY="a" * 64)
