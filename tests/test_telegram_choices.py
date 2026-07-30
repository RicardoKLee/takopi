import pytest

from takopi.progress import ProgressTracker
from takopi.runner_bridge import ExecBridgeConfig
from takopi.markdown import MarkdownPresenter
from takopi.telegram.bridge import (
    CHOICE_CALLBACK_PREFIX,
    CHOICE_INPUT_CALLBACK_PREFIX,
    CLEAR_MARKUP,
    TelegramBridgeConfig,
    TelegramPresenter,
    build_choice_markup,
    detect_choice_options,
    run_main_loop,
)
from takopi.telegram.loop import _strip_bot_mention_prefix
from takopi.transport_runtime import TransportRuntime
from takopi.runners.mock import Return, ScriptRunner
from takopi.telegram.types import TelegramCallbackQuery, TelegramIncomingMessage
from tests.telegram_fakes import FakeBot, FakeTransport, _empty_projects, _make_router

CODEX_ENGINE = "codex"


def test_detect_choice_options_basic() -> None:
    options = detect_choice_options("A. one\nB. two\nC. three")
    assert options is not None
    assert [(option.letter, option.text) for option in options] == [
        ("A", "one"),
        ("B", "two"),
        ("C", "three"),
    ]
    assert all(option.needs_input is False for option in options)


def test_detect_choice_options_bold_and_parens() -> None:
    options = detect_choice_options("**A**. one\n**B.)** two\n**C**）three")
    assert options is not None
    assert [option.letter for option in options] == ["A", "B", "C"]


def test_detect_choice_options_list_markers() -> None:
    options = detect_choice_options("- A) one\n- B) two")
    assert options is not None
    assert [option.letter for option in options] == ["A", "B"]


def test_detect_choice_options_fullwidth_punctuation() -> None:
    options = detect_choice_options("A．one\nB）two")
    assert options is not None
    assert [option.letter for option in options] == ["A", "B"]


def test_detect_choice_options_ignores_code_fence() -> None:
    text = "```\nA. one\nB. two\n```\nplain text"
    assert detect_choice_options(text) is None


def test_detect_choice_options_requires_two_consecutive_from_a() -> None:
    assert detect_choice_options("A. only one") is None
    assert detect_choice_options("B. one\nC. two") is None
    assert detect_choice_options("no options here") is None
    assert detect_choice_options("") is None


def test_detect_choice_options_restarts_on_later_block() -> None:
    text = "A. prose mention\n\nexplanation\n\nA. real one\nB. real two"
    options = detect_choice_options(text)
    assert options is not None
    assert [(option.letter, option.text) for option in options] == [
        ("A", "real one"),
        ("B", "real two"),
    ]


def test_detect_choice_options_tolerates_surrounding_text() -> None:
    text = "pick one:\n\nA. one\nB. two\n\nreply with the letter."
    options = detect_choice_options(text)
    assert options is not None
    assert [option.letter for option in options] == ["A", "B"]


def test_detect_choice_options_needs_input_keywords() -> None:
    options = detect_choice_options("A. one\nB. 其他问题\nC. 输入内容\nD. 自定义")
    assert options is not None
    assert [option.needs_input for option in options] == [False, True, True, True]


def test_build_choice_markup_callback_buttons() -> None:
    options = detect_choice_options("A. one\nB. two")
    assert options is not None
    markup = build_choice_markup(options)
    assert markup == {
        "inline_keyboard": [
            [
                {"text": "A", "callback_data": f"{CHOICE_CALLBACK_PREFIX}A"},
                {"text": "B", "callback_data": f"{CHOICE_CALLBACK_PREFIX}B"},
            ]
        ]
    }


def test_build_choice_markup_input_options_use_input_callback() -> None:
    options = detect_choice_options("A. one\nB. 其他问题")
    assert options is not None
    markup = build_choice_markup(options)
    assert markup == {
        "inline_keyboard": [
            [
                {"text": "A", "callback_data": f"{CHOICE_CALLBACK_PREFIX}A"},
                {"text": "B", "callback_data": f"{CHOICE_INPUT_CALLBACK_PREFIX}B"},
            ]
        ]
    }


def test_build_choice_markup_wraps_rows() -> None:
    options = detect_choice_options("A. 1\nB. 2\nC. 3\nD. 4\nE. 5")
    assert options is not None
    markup = build_choice_markup(options)
    rows = markup["inline_keyboard"]
    assert [len(row) for row in rows] == [4, 1]


def _progress_state():
    tracker = ProgressTracker(engine=CODEX_ENGINE)
    return tracker.snapshot()


def test_render_final_attaches_choice_markup() -> None:
    presenter = TelegramPresenter()
    rendered = presenter.render_final(
        _progress_state(),
        elapsed_s=1.0,
        status="done",
        answer="pick one:\nA. one\nB. two",
    )
    assert rendered.extra["reply_markup"] == {
        "inline_keyboard": [
            [
                {"text": "A", "callback_data": f"{CHOICE_CALLBACK_PREFIX}A"},
                {"text": "B", "callback_data": f"{CHOICE_CALLBACK_PREFIX}B"},
            ]
        ]
    }


def test_render_final_plain_answer_clears_markup() -> None:
    presenter = TelegramPresenter()
    rendered = presenter.render_final(
        _progress_state(),
        elapsed_s=1.0,
        status="done",
        answer="just a plain answer",
    )
    assert rendered.extra["reply_markup"] == CLEAR_MARKUP


def test_render_final_error_status_clears_markup() -> None:
    presenter = TelegramPresenter()
    rendered = presenter.render_final(
        _progress_state(),
        elapsed_s=1.0,
        status="error",
        answer="A. one\nB. two",
    )
    assert rendered.extra["reply_markup"] == CLEAR_MARKUP


def test_strip_bot_mention_prefix() -> None:
    assert _strip_bot_mention_prefix("@bot A extra", "bot") == "A extra"
    assert _strip_bot_mention_prefix("@Bot A", "bot") == "A"
    assert _strip_bot_mention_prefix("@bot", "bot") == ""
    assert _strip_bot_mention_prefix("@botter A", "bot") == "@botter A"
    assert _strip_bot_mention_prefix("hello @bot", "bot") == "hello @bot"
    assert _strip_bot_mention_prefix("@bot A", None) == "@bot A"


def _make_cfg(
    transport: FakeTransport,
    runner: ScriptRunner,
    *,
    bot: FakeBot | None = None,
) -> TelegramBridgeConfig:
    runtime = TransportRuntime(router=_make_router(runner), projects=_empty_projects())
    return TelegramBridgeConfig(
        bot=bot or FakeBot(),
        runtime=runtime,
        chat_id=123,
        startup_msg="",
        exec_cfg=ExecBridgeConfig(
            transport=transport,
            presenter=MarkdownPresenter(),
            final_notify=True,
        ),
        forward_coalesce_s=0.0,
        media_group_debounce_s=0.0,
    )


@pytest.mark.anyio
async def test_run_main_loop_choice_callback_dispatches_letter() -> None:
    transport = FakeTransport()
    bot = FakeBot()
    runner = ScriptRunner([Return(answer="ok")], engine=CODEX_ENGINE)
    cfg = _make_cfg(transport, runner, bot=bot)

    async def poller(_cfg: TelegramBridgeConfig):
        yield TelegramCallbackQuery(
            transport="telegram",
            chat_id=123,
            message_id=900,
            callback_query_id="cbq-1",
            data=f"{CHOICE_CALLBACK_PREFIX}B",
            sender_id=123,
            raw={
                "message": {
                    "text": "pick one\nA. one\nB. two",
                    "chat": {"type": "private"},
                }
            },
            update_id=1,
        )

    await run_main_loop(cfg, poller)

    assert len(runner.calls) == 1
    assert runner.calls[0][0] == "B"
    assert bot.callback_calls[0]["callback_query_id"] == "cbq-1"
    assert bot.edit_markup_calls == [
        {"chat_id": 123, "message_id": 900, "reply_markup": CLEAR_MARKUP}
    ]


@pytest.mark.anyio
async def test_run_main_loop_choice_callback_resumes_from_message() -> None:
    transport = FakeTransport()
    bot = FakeBot()
    runner = ScriptRunner([Return(answer="ok")], engine=CODEX_ENGINE)
    cfg = _make_cfg(transport, runner, bot=bot)

    async def poller(_cfg: TelegramBridgeConfig):
        yield TelegramCallbackQuery(
            transport="telegram",
            chat_id=123,
            message_id=900,
            callback_query_id="cbq-2",
            data=f"{CHOICE_CALLBACK_PREFIX}A",
            sender_id=123,
            raw={
                "message": {
                    "text": "pick one\n`codex resume c-123`",
                    "chat": {"type": "private"},
                }
            },
            update_id=1,
        )

    await run_main_loop(cfg, poller)

    assert len(runner.calls) == 1
    assert runner.calls[0][0] == "A"
    assert runner.calls[0][1] is not None
    assert runner.calls[0][1].value == "c-123"


@pytest.mark.anyio
async def test_run_main_loop_strips_bot_mention_prefix() -> None:
    transport = FakeTransport()
    bot = FakeBot()
    runner = ScriptRunner([Return(answer="ok")], engine=CODEX_ENGINE)
    cfg = _make_cfg(transport, runner, bot=bot)

    async def poller(_cfg: TelegramBridgeConfig):
        yield TelegramIncomingMessage(
            transport="telegram",
            chat_id=123,
            message_id=42,
            text="@bot B extra detail",
            reply_to_message_id=None,
            reply_to_text=None,
            sender_id=123,
            chat_type="private",
        )

    await run_main_loop(cfg, poller)

    assert len(runner.calls) == 1
    assert runner.calls[0][0] == "B extra detail"

@pytest.mark.anyio
async def test_run_main_loop_choice_input_callback_prompts_for_text() -> None:
    transport = FakeTransport()
    bot = FakeBot()
    runner = ScriptRunner([Return(answer="ok")], engine=CODEX_ENGINE)
    cfg = _make_cfg(transport, runner, bot=bot)

    async def poller(_cfg: TelegramBridgeConfig):
        yield TelegramCallbackQuery(
            transport="telegram",
            chat_id=123,
            message_id=900,
            callback_query_id="cbq-input",
            data=f"{CHOICE_INPUT_CALLBACK_PREFIX}B",
            sender_id=123,
            raw={
                "message": {
                    "text": "pick one\nA. one\nB. 其他问题",
                    "chat": {"type": "private"},
                }
            },
            update_id=1,
        )

    await run_main_loop(cfg, poller)

    assert runner.calls == []
    assert bot.callback_calls[0]["callback_query_id"] == "cbq-input"
    assert bot.edit_markup_calls == [
        {"chat_id": 123, "message_id": 900, "reply_markup": CLEAR_MARKUP}
    ]
    assert len(bot.send_calls) == 1
    assert bot.send_calls[0]["reply_markup"] == {
        "force_reply": True,
        "selective": True,
        "input_field_placeholder": "B …",
    }


@pytest.mark.anyio
async def test_run_main_loop_choice_input_followup_sends_letter_and_text() -> None:
    transport = FakeTransport()
    bot = FakeBot()
    runner = ScriptRunner([Return(answer="ok")], engine=CODEX_ENGINE)
    cfg = _make_cfg(transport, runner, bot=bot)

    async def poller(_cfg: TelegramBridgeConfig):
        yield TelegramCallbackQuery(
            transport="telegram",
            chat_id=123,
            message_id=900,
            callback_query_id="cbq-input-2",
            data=f"{CHOICE_INPUT_CALLBACK_PREFIX}B",
            sender_id=55,
            raw={
                "message": {
                    "text": "pick one\n`codex resume c-9`",
                    "chat": {"type": "private"},
                }
            },
            update_id=1,
        )
        yield TelegramIncomingMessage(
            transport="telegram",
            chat_id=123,
            message_id=1001,
            text="自定义细节",
            reply_to_message_id=1,
            reply_to_text="请输入选项 B 的补充内容：",
            sender_id=55,
            chat_type="private",
            update_id=2,
        )

    await run_main_loop(cfg, poller)

    assert len(runner.calls) == 1
    assert runner.calls[0][0] == "B 自定义细节"
    assert runner.calls[0][1] is not None
    assert runner.calls[0][1].value == "c-9"

