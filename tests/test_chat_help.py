from __future__ import annotations

from takopi.chat_help import ChatHelpOptions, format_chat_help


def test_format_chat_help_includes_core_commands() -> None:
    text = format_chat_help(
        ChatHelpOptions(
            transport="telegram",
            engine_ids=("claude", "cursor", "qoder"),
            project_aliases=("sandbox",),
            default_engine="claude",
            include_file=True,
            include_topics=True,
            files_enabled=True,
        )
    )
    assert "/help" in text
    assert "/agent" in text
    assert "/model" in text
    assert "/ctx" in text
    assert "/topic" in text
    assert "/file get" in text
    assert "claude" in text
    assert "sandbox" in text


def test_format_chat_help_feishu_note() -> None:
    text = format_chat_help(
        ChatHelpOptions(
            transport="feishu",
            engine_ids=("qoder",),
            project_aliases=(),
            default_engine="qoder",
        )
    )
    assert "feishu" in text.lower()
    assert "@bot" in text


def test_format_chat_help_file_disabled() -> None:
    text = format_chat_help(
        ChatHelpOptions(
            transport="discord",
            engine_ids=("claude",),
            project_aliases=(),
            default_engine="claude",
            include_file=True,
            files_enabled=False,
        )
    )
    assert "enable" in text.lower()
    assert "/file get" not in text
