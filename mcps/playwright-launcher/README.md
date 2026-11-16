# playwright-launcher

Opens and closes the residential-proxy Chromium that the **Playwright MCP**
drives over CDP at `127.0.0.1:9222`. Two servers work together: this one starts
and stops the browser; `@playwright/mcp` reads pages inside it.

## Tools

| Tool | Action |
|---|---|
| `playwright_status` | Report running state, CDP port state, and the live exit IP. Changes nothing. |
| `playwright_open` | Launch the browser if it is down, wait for the CDP port, then verify the proxy exit IP. **Fails** if the IP is not the expected one. |
| `playwright_close` | `SIGTERM` any Chromium on the profile so cookies are written. Never `kill -9`. |

## Fail-closed

`playwright_open` reads `PROXY_EXIT_IP` from the repo root `.env` and refuses to
hand over the browser if the live exit IP does not match. A dead phone proxy
therefore cannot send a read out through the wrong address.

## Config (repo root `.env`)

| Key | Meaning |
|---|---|
| `PROXY_EXIT_IP` | The required residential exit IP. `playwright_open` fails if the live IP differs. |
| `PROXY_SOCKS5_PORT` | The local SOCKS5 port used for the IP check. Default `1080`. |
| `XBROWSER_PATH` | The browser launcher this server starts. |
| `XBROWSER_LOG` | Where the launched browser writes stdout/stderr. |
| `XBROWSER_DISPLAY` | The X display the browser uses. |
| `XBROWSER_CDP_PORT` | The CDP port the Playwright MCP connects to. |
| `XBROWSER_PROFILE_PATTERN` | The `pgrep`/`pkill` pattern that finds the browser. |

See `.env.example` for placeholder values.

## Register (global / user scope)

```bash
claude mcp add -s user playwright-launcher -- \
  uv run --directory /path/to/repo/mcps/playwright-launcher fastmcp run server.py
```

The Playwright MCP stays registered separately:

```bash
claude mcp add -s user playwright -- \
  npx @playwright/mcp@latest --cdp-endpoint http://127.0.0.1:9222
```
