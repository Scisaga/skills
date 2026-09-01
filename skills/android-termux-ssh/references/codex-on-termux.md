# Codex on native Termux

## Scope and support boundary

Codex CLI running inside Termux can invoke `termux-*`, Git, network tools and the local Bluetooth helper directly through the shell. Same-device control does not require MCP.

OpenAI documents Codex CLI for macOS, Linux and Windows, not Android/Termux. Treat native Android as a compatibility deployment and verify every target device. Do not silently install a community-modified Codex binary.

Official references: [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), [authentication](https://learn.chatgpt.com/docs/auth), and [sandboxing and approvals](https://learn.chatgpt.com/docs/sandboxing).

## Install and configure

Run inside Termux:

```bash
bash configure-codex.sh --proxy http://PROXY_HOST:PORT
```

On Android, npm reports `process.platform=android` and therefore does not automatically install the optional runtime package restricted to `os=linux`. The Codex launcher maps Android ARM64/x64 to the corresponding Linux musl target. The script first installs the official `@openai/codex` main package, reads its installed version, then installs the exact matching official Linux runtime under the alias expected by the launcher. It validates the main package, aliased runtime and `codex --version` as one version set. Never mix versions or let two installation methods compete on `PATH`.

If the user explicitly accepts unsandboxed commands because the Android kernel rejects Codex's Linux sandbox:

```bash
bash configure-codex.sh \
  --proxy http://PROXY_HOST:PORT \
  --no-sandbox
```

`--no-sandbox` persists:

```toml
approval_policy = "on-request"
sandbox_mode = "danger-full-access"
```

If the user explicitly requests Codex **Full access**, use the distinct option:

```bash
bash configure-codex.sh \
  --proxy http://PROXY_HOST:PORT \
  --full-access
```

Full access has the official meaning below; it removes approval prompts as well as the sandbox:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

The visible SSH label `root` is still only the Termux application UID. Disabling Codex's sandbox grants commands the full Termux UID, including its private home, shared-storage grants and delegated Termux:API capabilities; it does not grant Android UID 0.

## Proxy and CA

The script writes a mode-`0600` environment file at `~/.config/android-termux-ssh/network-env.sh` and sources it before the non-interactive guard in `~/.bashrc`.

It also replaces npm's `codex` symlink with a small managed launcher that sources this environment and then executes the official npm JavaScript launcher. This makes `codex`, including non-interactive SSH invocations, use the same proxy and CA. Rerun `configure-codex.sh` after any manual `npm update`, because npm can restore its own symlink.

- Use `CODEX_CA_CERTIFICATE` for a complete readable PEM CA bundle; never disable TLS verification. If an organization supplies only a private root certificate, append it to a private copy of Termux's system bundle instead of replacing all public roots or setting `strict-ssl=false`/`NODE_TLS_REJECT_UNAUTHORIZED=0`.
- During installation, the helper exports the proxy before `pkg`/`npm` and supplies the same PEM bundle through `SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS` and npm's `cafile` setting. This keeps package installation compatible with private or updated CA roots without disabling verification.
- Keep `localhost`, `127.0.0.1` and `::1` in `NO_PROXY`. Otherwise the Bluetooth helper's `127.0.0.1:18765` request can be sent to the egress proxy and return a misleading HTTP 502.
- Keep approved private subnets in `NO_PROXY` so local IoT HTTP requests do not leave the device through an upstream proxy.
- A proxy URL containing credentials is sensitive. Do not write it to `AGENTS.md`, logs, the repository or shared storage.

## Authentication

Prefer ChatGPT device-code login for a tablet:

```bash
codex login --device-auth
codex login status
```

Device-code authorization must first be enabled in ChatGPT **web** security settings for a personal account, or by a workspace administrator. The Android ChatGPT app may not expose this switch.

Treat `~/.codex/auth.json` like a password. Keep it in Termux private storage with mode `0600`; never copy it into `~/workspace` or `/storage/emulated/0`.

## Verification

```bash
codex --version
codex login status
codex doctor
codex sandbox linux -- "$PREFIX/bin/true"
```

If the sandbox command fails with `bwrap: Can't read /proc/sys/kernel/overflowuid: Permission denied`, the Android kernel/SELinux path is incompatible. Only apply `--no-sandbox` after explicit user approval.

The ordinary verifier checks package integrity, authentication metadata, policy values, proxy exclusions, CA readability and secret-file modes without sending a model request. Treat the sandbox command above as a diagnostic only; it is not a passing gate after the user has explicitly selected an unsandboxed policy.

For a no-write model smoke test:

```bash
codex exec --ephemeral --skip-git-repo-check \
  'Do not call tools. Reply with exactly: CODEX_MODEL_OK'
```

In unsandboxed `codex exec`, approvals are non-interactive and may be reported as `never`. Do not use it for broad unattended prompts. If Full access is not explicitly required, prefer the interactive TUI with `approval_policy="on-request"`; in either mode, scope recurring automation to audited helper commands.

## Device-agent pattern

- Keep `~/AGENTS.md` current so Codex understands the Android UID, shared-storage, camera, Wi-Fi and Bluetooth boundaries.
- Put ordinary Git repositories in `~/workspace` only when Android apps must see them; keep files requiring real POSIX semantics under private `$HOME`.
- For recurring probe actions, provide narrow commands such as DNS/HTTP/TCP checks, Wi-Fi scan summaries, BLE scan summaries and explicit MQTT/HTTP actions instead of exposing a public raw-shell endpoint.
- Do not expose Codex app-server, SSH or an MCP `shell(command)` tool to the public Internet. SSH remains an optional maintenance path; the tablet can run Codex locally without a laptop.
