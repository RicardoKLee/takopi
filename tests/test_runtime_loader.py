from pathlib import Path

import pytest

import takopi.runtime_loader as runtime_loader
from takopi.config import ConfigError
from takopi.settings import TakopiSettings


def test_build_runtime_spec_minimal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runtime_loader.shutil, "which", lambda _cmd: "/bin/echo")
    settings = TakopiSettings.model_validate(
        {
            "transport": "telegram",
            "watch_config": True,
            "transports": {"telegram": {"bot_token": "token", "chat_id": 123}},
        }
    )
    config_path = tmp_path / "takopi.toml"
    config_path.write_text(
        'transport = "telegram"\n\n[transports.telegram]\n'
        'bot_token = "token"\nchat_id = 123\n',
        encoding="utf-8",
    )

    spec = runtime_loader.build_runtime_spec(
        settings=settings,
        config_path=config_path,
    )

    assert spec.router.default_engine == settings.default_engine
    runtime = spec.to_runtime(config_path=config_path)
    assert runtime.default_engine == settings.default_engine
    assert runtime.watch_config is True


def test_build_runtime_spec_falls_back_when_default_cli_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Only `pi` is installed on this host; the configured default `codex` is not.
    monkeypatch.setattr(
        runtime_loader.shutil,
        "which",
        lambda cmd: "/bin/pi" if cmd == "pi" else None,
    )
    settings = TakopiSettings.model_validate(
        {
            "transport": "telegram",
            "transports": {"telegram": {"bot_token": "token", "chat_id": 123}},
        }
    )
    config_path = tmp_path / "takopi.toml"
    config_path.write_text(
        'transport = "telegram"\n\n[transports.telegram]\n'
        'bot_token = "token"\nchat_id = 123\n',
        encoding="utf-8",
    )

    spec = runtime_loader.build_runtime_spec(
        settings=settings,
        config_path=config_path,
    )

    # Startup must not fail; the unavailable default falls back to first usable.
    assert spec.router.default_engine == "pi"
    runtime = spec.to_runtime(config_path=config_path)
    assert runtime.available_engine_ids() == ("pi",)


def test_resolve_default_engine_unknown(tmp_path: Path) -> None:
    settings = TakopiSettings.model_validate(
        {
            "transport": "telegram",
            "transports": {"telegram": {"bot_token": "token", "chat_id": 123}},
        }
    )
    with pytest.raises(ConfigError, match="Unknown default engine"):
        runtime_loader.resolve_default_engine(
            override="unknown",
            settings=settings,
            config_path=tmp_path / "takopi.toml",
            engine_ids=["codex"],
        )
