# takopi

🐙 *he just wants to help-pi*

chat bridge for codex, claude code, cursor, qoder, opencode, pi. manage multiple projects and worktrees, stream progress, and resume sessions anywhere.

## features

- projects and worktrees: work on multiple repos/branches simultaneously, branches are git worktrees
- stateless resume: continue in chat or copy the resume line to pick up in terminal
- progress streaming: commands, tools, file changes, elapsed time
- parallel runs across agent sessions, per-agent-session queue with Codex steering/cancel controls
- works with telegram features like voice notes and scheduled messages
- file transfer: send files to the repo or fetch files/dirs back
- group chats and topics: create a forum topic per issue with `/topic <issue title>`, target repos/branches per task
- works with existing anthropic and openai subscriptions

## requirements

`uv` for installation (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

python 3.14+ (`uv python install 3.14`)

at least one engine on PATH: `codex`, `claude`, `cursor`, `qoder`, `opencode`, or `pi`

## install

```sh
uv tool install -U takopi
```

for this fork, install core + plugins:

```sh
git clone git@github.com:RicardoKLee/takopi.git
cd takopi
TAKOPI_PY="$(uv tool dir takopi 2>/dev/null)/bin/python3"
# fallback if takopi not yet installed via uv tool:
TAKOPI_PY="${TAKOPI_PY:-$(dirname "$(which takopi)")/python3}"

# core (telegram + codex/claude/opencode/pi)
uv pip install -e . --python "$TAKOPI_PY"

# fork plugins (separate public repos; not on PyPI yet — install from GitHub)
uv pip install "takopi-engine-cursor @ git+https://github.com/RicardoKLee/takopi-engine-cursor.git" --python "$TAKOPI_PY"
uv pip install "takopi-engine-qoder @ git+https://github.com/RicardoKLee/takopi-engine-qoder.git" --python "$TAKOPI_PY"
uv pip install "takopi-transport-feishu @ git+https://github.com/RicardoKLee/takopi-transport-feishu.git" --python "$TAKOPI_PY"
uv pip install takopi-discord --python "$TAKOPI_PY"
```

for local plugin development, clone sibling repos and install editable:

```sh
git clone git@github.com:RicardoKLee/takopi-engine-cursor.git ../takopi-engine-cursor
git clone git@github.com:RicardoKLee/takopi-engine-qoder.git ../takopi-engine-qoder
git clone git@github.com:RicardoKLee/takopi-transport-feishu.git ../takopi-transport-feishu

uv pip install -e ../takopi-engine-cursor --python "$TAKOPI_PY"
uv pip install -e ../takopi-engine-qoder --python "$TAKOPI_PY"
uv pip install -e ../takopi-transport-feishu --python "$TAKOPI_PY"
```

## fork plugins

extensions ship as separate public packages (same pattern as `takopi-discord`):

| package | repo | type | id | install |
|---------|------|------|----|---------|
| `takopi-engine-cursor` | [RicardoKLee/takopi-engine-cursor](https://github.com/RicardoKLee/takopi-engine-cursor) | engine | `cursor` | git (see above) |
| `takopi-engine-qoder` | [RicardoKLee/takopi-engine-qoder](https://github.com/RicardoKLee/takopi-engine-qoder) | engine | `qoder` | git (see above) |
| `takopi-transport-feishu` | [RicardoKLee/takopi-transport-feishu](https://github.com/RicardoKLee/takopi-transport-feishu) | transport | `feishu` | git (see above) |
| `takopi-discord` | [asianviking/takopi-discord](https://github.com/asianviking/takopi-discord) | transport | `discord` | PyPI |

verify with:

```sh
takopi plugins --load
```

## setup

run `takopi` and follow the setup wizard. it will help you:

1. create a bot token via @BotFather (telegram) or configure feishu app credentials
2. pick a workflow (assistant, workspace, or handoff)
3. connect your chat
4. choose a default engine

workflows configure conversation mode, topics, and resume lines automatically:

- **assistant**: ongoing chat with auto-resume (recommended)
- **workspace**: forum topics per issue (`/topic <issue title>`), repos/branches chosen per task
- **handoff**: reply-to-continue with terminal resume lines

## usage

```sh
cd ~/dev/happy-gadgets
takopi cursor --transport telegram
```

other transports:

```sh
takopi cursor --transport feishu --no-onboard
takopi cursor --transport discord
```

send a message to your bot. prefix with `/codex`, `/claude`, `/cursor`, `/qoder`, `/opencode`, or `/pi` to pick an engine. reply to continue a thread.

send `/help` in chat to list available commands, engines, and project aliases for your transport.

register a project with `takopi init happy-gadgets`, then target it from anywhere with `/happy-gadgets hard reset the timeline`.

mention a branch to run an agent in a dedicated worktree `/happy-gadgets @feat/memory-box freeze artifacts forever`.

inspect or update settings with `takopi config list`, `takopi config get`, and `takopi config set`.

see [takopi.dev](https://takopi.dev/) for configuration, worktrees, topics, file transfer, and more.

## process supervision

takopi transports are long-running processes. run them under a supervisor so they restart after crashes, survive logout, and come back after reboot.

### pm2 (recommended for quick setup)

install pm2, then start one process per transport:

```sh
pm2 start "takopi cursor --transport telegram" --name takopi-telegram
pm2 start "takopi cursor --transport feishu --no-onboard" --name takopi-feishu
pm2 start "takopi cursor --transport discord" --name takopi-discord
```

common operations:

```sh
pm2 list
pm2 restart takopi-telegram takopi-feishu takopi-discord
pm2 logs takopi-telegram --lines 100
pm2 save          # persist the process list
pm2 startup       # generate boot-time autostart (run the printed command once)
```

pm2 restarts a process when it exits unexpectedly. use `pm2 logs` to inspect startup failures (missing config, invalid token, engine not on PATH).

### systemd

for a single transport, create a user unit such as `~/.config/systemd/user/takopi-telegram.service`:

```ini
[Unit]
Description=Takopi Telegram bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/takopi cursor --transport telegram
Restart=on-failure
RestartSec=5
Environment=HOME=%h

[Install]
WantedBy=default.target
```

enable and start it:

```sh
systemctl --user daemon-reload
systemctl --user enable --now takopi-telegram.service
systemctl --user status takopi-telegram.service
journalctl --user -u takopi-telegram.service -f
```

duplicate the unit per transport (`feishu`, `discord`) and adjust `ExecStart`. `Restart=on-failure` gives basic fault tolerance; pair with `loginctl enable-linger` if the service must stay up after logout.

## plugins

takopi supports entrypoint-based plugins for engines, transports, and commands.

see [`docs/how-to/write-a-plugin.md`](docs/how-to/write-a-plugin.md) and [`docs/reference/plugin-api.md`](docs/reference/plugin-api.md).

## development

```sh
# core
git clone git@github.com:RicardoKLee/takopi.git
cd takopi && uv sync && uv run pytest

# plugins (separate repos)
git clone git@github.com:RicardoKLee/takopi-engine-cursor.git && cd takopi-engine-cursor && uv run pytest
git clone git@github.com:RicardoKLee/takopi-engine-qoder.git && cd takopi-engine-qoder && uv run pytest
git clone git@github.com:RicardoKLee/takopi-transport-feishu.git && cd takopi-transport-feishu && uv run pytest
```

after changing plugins, reinstall editable packages and restart PM2 transports.

see [`docs/reference/specification.md`](docs/reference/specification.md) and [`docs/developing.md`](docs/developing.md).
