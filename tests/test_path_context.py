"""Tests for path-based run contexts (arbitrary directory switching)."""

from __future__ import annotations

from pathlib import Path

import pytest

from takopi.config import ProjectConfig, ProjectsConfig
from takopi.context import RunContext
from takopi.directives import (
    DirectiveError,
    format_context_line,
    is_path_directive_token,
    parse_context_line,
    parse_directives,
)
from takopi.worktrees import WorktreeError, resolve_run_cwd, validate_context_path


def _projects() -> ProjectsConfig:
    return ProjectsConfig(projects={}, default_project=None)


# ---------------------------------------------------------------------------
# token classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("~", True),
        ("~/dev/repo", True),
        ("./here", True),
        ("../up", True),
        ("/home/user/repo", True),
        ("/claude", False),
        ("/z80", False),
        ("@branch", False),
        ("repo", False),
        ("/tmp", False),  # single-segment absolute path is not a directive
    ],
)
def test_is_path_directive_token(token: str, expected: bool) -> None:
    assert is_path_directive_token(token) is expected


# ---------------------------------------------------------------------------
# parse_directives
# ---------------------------------------------------------------------------


def test_parse_directives_path_consumed(tmp_path: Path) -> None:
    directives = parse_directives(
        f"{tmp_path} fix the bug",
        engine_ids=("claude",),
        projects=_projects(),
    )
    assert directives.path == str(tmp_path)
    assert directives.project is None
    assert directives.branch is None
    assert directives.prompt == "fix the bug"


def test_parse_directives_engine_and_path(tmp_path: Path) -> None:
    directives = parse_directives(
        f"/claude {tmp_path} do it",
        engine_ids=("claude", "codex"),
        projects=_projects(),
    )
    assert directives.engine == "claude"
    assert directives.path == str(tmp_path)
    assert directives.prompt == "do it"


def test_parse_directives_path_with_branch_rejected(tmp_path: Path) -> None:
    with pytest.raises(DirectiveError, match="cannot combine path and branch"):
        parse_directives(
            f"{tmp_path} @feat work",
            engine_ids=(),
            projects=_projects(),
        )


def test_parse_directives_project_with_path_rejected(tmp_path: Path) -> None:
    projects = ProjectsConfig(projects={}, default_project=None)
    projects.projects["z80"] = ProjectConfig(
        alias="z80", path=tmp_path, worktrees_dir=Path(".worktrees")
    )
    with pytest.raises(DirectiveError, match="cannot combine project and path"):
        parse_directives(
            f"/z80 {tmp_path} work",
            engine_ids=(),
            projects=projects,
        )


def test_parse_directives_multiple_paths_rejected(tmp_path: Path) -> None:
    with pytest.raises(DirectiveError, match="multiple path directives"):
        parse_directives(
            f"{tmp_path} {tmp_path} work",
            engine_ids=(),
            projects=_projects(),
        )


def test_parse_directives_missing_path_rejected() -> None:
    with pytest.raises(DirectiveError, match="path not found"):
        parse_directives(
            "/definitely/not/here work",
            engine_ids=(),
            projects=_projects(),
        )


def test_parse_directives_path_disabled_keeps_prompt(tmp_path: Path) -> None:
    directives = parse_directives(
        "./relative/arg",
        engine_ids=(),
        projects=_projects(),
        allow_path_directives=False,
    )
    assert directives.path is None
    assert directives.prompt == "./relative/arg"


# ---------------------------------------------------------------------------
# ctx: footer roundtrip
# ---------------------------------------------------------------------------


def test_context_line_roundtrip_path(tmp_path: Path) -> None:
    ctx = RunContext(path=tmp_path)
    line = format_context_line(ctx, projects=_projects())
    assert line == f"`ctx: {tmp_path}`"
    parsed = parse_context_line(line, projects=_projects())
    assert parsed == RunContext(path=tmp_path)


def test_context_line_missing_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(DirectiveError, match="path not found"):
        parse_context_line("`ctx: /definitely/not/here`", projects=_projects())


def test_context_line_project_still_works() -> None:
    projects = ProjectsConfig(projects={}, default_project=None)
    projects.projects["z80"] = ProjectConfig(
        alias="z80", path=Path("/tmp/z80"), worktrees_dir=Path(".worktrees")
    )
    parsed = parse_context_line("`ctx: z80 @feat`", projects=projects)
    assert parsed == RunContext(project="z80", branch="feat")


# ---------------------------------------------------------------------------
# resolve_run_cwd / validate_context_path
# ---------------------------------------------------------------------------


def test_resolve_run_cwd_path_context(tmp_path: Path) -> None:
    cwd = resolve_run_cwd(RunContext(path=tmp_path), projects=_projects())
    assert cwd == tmp_path.resolve()


def test_resolve_run_cwd_rejects_missing_path() -> None:
    with pytest.raises(WorktreeError, match="path not found"):
        resolve_run_cwd(
            RunContext(path=Path("/definitely/not/here")), projects=_projects()
        )


def test_resolve_run_cwd_rejects_file(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hi")
    with pytest.raises(WorktreeError, match="not a directory"):
        resolve_run_cwd(RunContext(path=target), projects=_projects())


def test_validate_context_path_rejects_root() -> None:
    with pytest.raises(WorktreeError, match="root"):
        validate_context_path("/")


def test_resolve_run_cwd_rejects_path_with_project(tmp_path: Path) -> None:
    with pytest.raises(WorktreeError, match="cannot be combined"):
        resolve_run_cwd(
            RunContext(project="z80", path=tmp_path), projects=_projects()
        )


# ---------------------------------------------------------------------------
# telegram chat prefs persistence
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_prefs_path_context_roundtrip(tmp_path: Path) -> None:
    from takopi.telegram.chat_prefs import ChatPrefsStore

    store = ChatPrefsStore(tmp_path / "telegram_chat_prefs_state.json")
    await store.set_context(123, RunContext(path=tmp_path))
    loaded = await store.get_context(123)
    assert loaded == RunContext(path=tmp_path)

    # switching from path back to project clears the path
    await store.set_context(123, RunContext(project="z80", branch="dev"))
    loaded = await store.get_context(123)
    assert loaded == RunContext(project="z80", branch="dev")

    await store.clear_context(123)
    assert await store.get_context(123) is None


@pytest.mark.anyio
async def test_chat_prefs_legacy_state_still_loads(tmp_path: Path) -> None:
    from takopi.telegram.chat_prefs import ChatPrefsStore, resolve_prefs_path

    cfg_path = tmp_path / "takopi.toml"
    state_path = resolve_prefs_path(cfg_path)
    state_path.write_text(
        '{"version": 1, "chats": {"123": {"context_project": "z80", '
        '"context_branch": "dev"}}}',
        encoding="utf-8",
    )
    store = ChatPrefsStore(state_path)
    loaded = await store.get_context(123)
    assert loaded == RunContext(project="z80", branch="dev")


def test_parse_chat_ctx_args_accepts_path(tmp_path: Path) -> None:
    from takopi.telegram.commands.topics import _parse_chat_ctx_args

    class _FakeRuntime:
        default_project = None

        def normalize_project_key(self, value: str) -> str | None:
            return None

    context, error = _parse_chat_ctx_args(
        str(tmp_path), runtime=_FakeRuntime(), default_project=None
    )
    assert error is None
    assert context == RunContext(path=tmp_path)

    context, error = _parse_chat_ctx_args(
        "/definitely/not/here", runtime=_FakeRuntime(), default_project=None
    )
    assert context is None
    assert "path not found" in error

    context, error = _parse_chat_ctx_args(
        f"{tmp_path} extra", runtime=_FakeRuntime(), default_project=None
    )
    assert context is None
    assert "does not take extra arguments" in error
