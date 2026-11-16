# WhatsApp MCP — how this instance is configured on the VPS

> Deployment record for the live instance on the VPS `signal` (Oracle Cloud,
> **ARM64**, Ubuntu 24.04). Built 12 August 2026. Read this before you touch
> the service. `VPS_SETUP.md` is the generic x86 guide — several of its steps
> were changed here, on purpose. **No secrets in this file** — the token is in
> `.env` at the **repo root**, mode 600.

## Architecture

```
[Claude Code / MCP client] --HTTP over tailnet--> [<tailnet-ip>:23380 fastmcp]
                                                        |
                                              localhost:23373 Beeper Desktop API
                                                        |
                                    Beeper Desktop (headless, Xvfb :99 + openbox)
```

Get the tailnet address with `tailscale ip -4`. Nothing listens on the public
address except sshd. No cloud firewall rule was added.

## Differences from VPS_SETUP.md — do not "fix" these

1. **ARM64, not x86.** The AppImage is `Beeper-*-arm64.AppImage`, downloaded
   from `https://api.beeper.com/desktop/download/linux/arm64/stable/com.automattic.beeper.desktop`
   (the guide's x64 URL now redirects to a marketing page). Stable symlink:
   `~/Downloads/Beeper.AppImage`.
2. **`dbus-run-session` wrapper.** Beeper crashes (SIGTRAP) on this host
   without a D-Bus session. `beeper.service` starts it as
   `dbus-run-session -- ~/Downloads/Beeper.AppImage --no-sandbox`.
3. **MCP binds to the tailnet address, not `0.0.0.0`.** Tailscale is the
   access control; there is no auth on the MCP itself. Never rebind to
   `0.0.0.0` and never open 23380 in the cloud firewall.
4. **Token location.** `BEEPER_ACCESS_TOKEN` lives in `.env` at the **repo
   root**, not in `mcps/whatsapp/.env` — `beeper_client.py` loads
   `parent.parent.parent / ".env"`. A token in the wrong place fails silently.
   Never put the token in a systemd unit or on a command line (`ps` and
   `systemctl show` are world-readable).
5. **`tags.json` must exist** next to `server.py` (minimum content: `{}`).
   The server reads it without a fallback; missing file = every tool call errors.
6. **Display stack is shared.** Xvfb `:99`, openbox (`wm.service`) and a
   passworded, tailnet-only x11vnc were already on this host for another
   project. Beeper reuses them. Do not create new display services and do not
   touch `x11vnc.service` (`-rfbauth`, tailnet bind — never `-nopw`).

## systemd units

`/etc/systemd/system/beeper.service` — `User=ubuntu`, `DISPLAY=:99`,
`After=xvfb.service wm.service`. Its `ExecStartPre` repoints the symlink at
the newest `Beeper-*-arm64.AppImage` on every start, so a Beeper auto-update
can never break boot (guide's pattern says `x86_64` and would never match here).

`/etc/systemd/system/whatsapp-mcp.service` — `User=ubuntu`,
`WorkingDirectory=<repo>/mcps/whatsapp`,
`ExecStart=~/.local/bin/uv run fastmcp run server.py --transport http --host <tailnet-ip> --port 23380`,
`RestrictAddressFamilies=AF_UNIX AF_INET` (blocks the hidden IPv6 wildcard
socket some servers open), `Requires=beeper.service`.

Both are `enabled` and survive reboot.

## Operation

```bash
systemctl status beeper whatsapp-mcp
curl http://localhost:23373/v1/info          # Beeper API up?
journalctl -u whatsapp-mcp -n 50 --no-pager  # MCP logs
sudo systemctl restart whatsapp-mcp          # after editing server.py
```

- After a restart of `whatsapp-mcp`, already-open Claude sessions hold a stale
  tool schema — reconnect (`/mcp`) or start a fresh session before using
  changed tools.
- A fresh Beeper only has recent messages. Older history and attachments
  appear after scrolling up in the chat over VNC (tailnet `:5900`, password —
  see the `automation_playwright` project's `.env`).
- Beeper version bump: nothing to do — the `ExecStartPre` self-heal retargets
  the symlink; `sudo systemctl restart beeper whatsapp-mcp` if it got stuck.
- Client registration:
  `claude mcp add -s user --transport http whatsapp http://<tailnet-ip>:23380/mcp`.

## Code facts worth knowing (state at commit 7f99ec7)

- Beeper 4.3+ renamed the Matrix account's network to `"Beeper"`;
  `_get_media_prefix()` matches both old and new names.
- `whatsapp_get_messages` prints attachments as `[token] "fileName"`;
  `whatsapp_download_files` accepts bare hash, prefixed token, or full
  `mxc://` URL (`_normalize_token`) and an optional `names` list so files
  save under their real names.
