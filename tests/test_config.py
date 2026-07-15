from app.config import Settings


def test_default_environment_is_dev() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "dev"
