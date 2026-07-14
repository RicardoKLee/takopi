from __future__ import annotations

from pathlib import Path

from takopi.api import EngineBackend, EngineConfig
from takopi.config import ConfigError
from takopi.runner import Runner

from .runner import CursorRunner


def build_runner(config: EngineConfig, config_path: Path) -> Runner:
    model = config.get("model")
    if model is not None and not isinstance(model, str):
        raise ConfigError(
            f"Invalid `cursor.model` in {config_path}; expected a string."
        )
    workspace = config.get("workspace")
    if workspace is not None and not isinstance(workspace, str):
        raise ConfigError(
            f"Invalid `cursor.workspace` in {config_path}; expected a string."
        )
    title = str(model) if model else "Cursor"
    return CursorRunner(model=model, workspace=workspace, title=title)


BACKEND = EngineBackend(
    id="cursor",
    build_runner=build_runner,
    cli_cmd="agent",
    install_cmd="curl https://cursor.com/install -fsS | bash",
)

__all__ = ["BACKEND", "build_runner"]
