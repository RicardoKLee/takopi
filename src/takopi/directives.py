from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ProjectsConfig
from .context import RunContext
from .model import EngineId
from .worktrees import WorktreeError, validate_context_path


@dataclass(frozen=True, slots=True)
class ParsedDirectives:
    prompt: str
    engine: EngineId | None
    project: str | None
    branch: str | None
    path: str | None


class DirectiveError(RuntimeError):
    pass


def is_path_directive_token(token: str) -> bool:
    """Classify a message token as a path directive.

    Recognized forms: `~`, `~/...`, `./...`, `../...`, and absolute paths
    (`/a/b...`, i.e. a leading `/` followed by at least one more separator).
    Plain names (engine/project aliases) never match.
    """
    if token == "~" or token.startswith(("~/", "./", "../")):
        return True
    if token.startswith("/") and "/" in token[1:]:
        return True
    return False


def _validate_path_directive(value: str) -> Path:
    try:
        return validate_context_path(value)
    except WorktreeError as exc:
        raise DirectiveError(str(exc)) from exc


def parse_directives(
    text: str,
    *,
    engine_ids: tuple[EngineId, ...],
    projects: ProjectsConfig,
    allow_path_directives: bool = True,
) -> ParsedDirectives:
    if not text:
        return ParsedDirectives(
            prompt="", engine=None, project=None, branch=None, path=None
        )

    lines = text.splitlines()
    idx = next((i for i, line in enumerate(lines) if line.strip()), None)
    if idx is None:
        return ParsedDirectives(
            prompt=text, engine=None, project=None, branch=None, path=None
        )

    line = lines[idx].lstrip()
    tokens = line.split()
    if not tokens:
        return ParsedDirectives(
            prompt=text, engine=None, project=None, branch=None, path=None
        )

    engine_map = {engine.lower(): engine for engine in engine_ids}
    project_map = {alias.lower(): alias for alias in projects.projects}

    engine: EngineId | None = None
    project: str | None = None
    branch: str | None = None
    path: str | None = None
    consumed = 0

    for token in tokens:
        if token.startswith("/") and not (
            allow_path_directives and is_path_directive_token(token)
        ):
            name = token[1:]
            if "@" in name:
                name = name.split("@", 1)[0]
            if not name:
                break
            key = name.lower()
            engine_candidate = engine_map.get(key)
            project_candidate = project_map.get(key)
            if engine_candidate is not None:
                if engine is not None:
                    raise DirectiveError("multiple engine directives")
                engine = engine_candidate
                consumed += 1
                continue
            if project_candidate is not None:
                if project is not None:
                    raise DirectiveError("multiple project directives")
                if path is not None:
                    raise DirectiveError("cannot combine project and path directives")
                project = project_candidate
                consumed += 1
                continue
            break
        if allow_path_directives and is_path_directive_token(token):
            if path is not None:
                raise DirectiveError("multiple path directives")
            if project is not None:
                raise DirectiveError("cannot combine project and path directives")
            if branch is not None:
                raise DirectiveError("cannot combine path and branch directives")
            _validate_path_directive(token)
            path = token
            consumed += 1
            continue
        if token.startswith("@"):
            value = token[1:]
            if not value:
                break
            if branch is not None:
                raise DirectiveError("multiple @branch directives")
            if path is not None:
                raise DirectiveError("cannot combine path and branch directives")
            branch = value
            consumed += 1
            continue
        break

    if consumed == 0:
        return ParsedDirectives(
            prompt=text, engine=None, project=None, branch=None, path=None
        )

    if consumed < len(tokens):
        remainder = " ".join(tokens[consumed:])
        lines[idx] = remainder
    else:
        lines.pop(idx)

    prompt = "\n".join(lines).strip()
    return ParsedDirectives(
        prompt=prompt, engine=engine, project=project, branch=branch, path=path
    )


def parse_context_line(
    text: str | None, *, projects: ProjectsConfig
) -> RunContext | None:
    if not text:
        return None
    ctx: RunContext | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("`") and stripped.endswith("`") and len(stripped) > 1:
            stripped = stripped[1:-1].strip()
        elif stripped.startswith("`"):
            stripped = stripped[1:].strip()
        elif stripped.endswith("`"):
            stripped = stripped[:-1].strip()
        if not stripped.lower().startswith("ctx:"):
            continue
        content = stripped.split(":", 1)[1].strip()
        if not content:
            continue
        tokens = content.split()
        if not tokens:
            continue
        first = tokens[0]
        if is_path_directive_token(first):
            # Path context: the whole remainder is the directory path
            # (paths may contain spaces; branch is not supported).
            resolved = _validate_path_directive(content)
            ctx = RunContext(path=resolved)
            continue
        project = tokens[0]
        branch = None
        if len(tokens) >= 2:
            if tokens[1] == "@" and len(tokens) >= 3:
                branch = tokens[2]
            elif tokens[1].startswith("@"):
                branch = tokens[1][1:]
        project_key = project.lower()
        if project_key not in projects.projects:
            raise DirectiveError(
                f"unknown project {project!r} in ctx line; start a new thread or "
                "add it back to your config"
            )
        ctx = RunContext(project=project_key, branch=branch)
    return ctx


def format_context_line(
    context: RunContext | None, *, projects: ProjectsConfig
) -> str | None:
    if context is None:
        return None
    if context.path is not None:
        return f"`ctx: {context.path}`"
    if context.project is None:
        return None
    project_cfg = projects.projects.get(context.project)
    alias = project_cfg.alias if project_cfg is not None else context.project
    if context.branch:
        return f"`ctx: {alias} @{context.branch}`"
    return f"`ctx: {alias}`"
