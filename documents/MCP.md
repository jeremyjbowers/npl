# NPL MCP

Agents can look up rosters, roster limits, players, draft picks, trades, the transaction ledger, open auctions, club finances, and your wishlist.

Filing a transaction is separate. A read-write key uses the same bearer token on `/api/v1/transactions/`. The MCP server itself is read-only.

Works with Claude, Codex, GitHub Copilot, Cursor, and any other client that speaks MCP.

## How it works

1. The site serves MCP at `https://YOUR-HOST/mcp` (Streamable HTTP).
2. You authenticate with a long-lived owner API key in the `Authorization: Bearer npl_…` header.
3. The client stores the URL and the key. There is no OAuth step.

The same key works on the JSON API under `/api/mcp/v1/…` if you want to curl the data without MCP. `/api/mcp/v1/` works on the ordinary WSGI site. Remote MCP clients need the ASGI app so `/mcp` is mounted.

## Generate or revoke a key

Sign in and open **API keys** (`/my/api-keys/`).

- **Generate key** creates a read key or a read-write key. The secret stays on that page, so you can copy it later. Only you can see your keys.
- **Revoke** turns a key off. A revoked key cannot call the API. The row stays so you can tell which agent you turned off.

A commissioner can also mint one from the shell:

```bash
export DJANGO_SETTINGS_MODULE=config.do_app_platform.settings
django-admin create_owner_api_token --list-owners
django-admin create_owner_api_token --email OWNER@EMAIL --label "claude" --scope read
```

Send the `npl_…` value privately. The owner can also read it on `/my/api-keys/`.

## Owner setup

```json
{
  "mcpServers": {
    "npl": {
      "url": "https://YOUR-NPL-HOST/mcp",
      "headers": {
        "Authorization": "Bearer npl_YOUR_TOKEN_HERE"
      }
    }
  }
}
```

| Client | Where this usually goes |
| --- | --- |
| Claude | Settings → Developer / MCP connectors |
| Codex | Remote MCP server settings |
| GitHub Copilot | MCP / agent tools |
| Cursor | Settings → MCP → `mcp.json` |

Look for a remote MCP URL plus a headers or Authorization field.

### Sanity check

```bash
curl -s -H "Authorization: Bearer npl_YOUR_TOKEN" \
  https://YOUR-NPL-HOST/mcp/health

curl -s -H "Authorization: Bearer npl_YOUR_TOKEN" \
  https://YOUR-NPL-HOST/api/mcp/v1/season/
```

`X-NPL-Token: npl_…` is accepted as well as the Authorization header.

## Optional stdio bridge

Use this only when a client cannot do remote HTTPS MCP. It calls the same JSON API.

```json
{
  "mcpServers": {
    "npl": {
      "command": "django-admin",
      "args": ["mcp_serve"],
      "env": {
        "DJANGO_SETTINGS_MODULE": "config.dev.settings",
        "NPL_API_URL": "https://YOUR-NPL-HOST",
        "NPL_API_TOKEN": "npl_YOUR_TOKEN_HERE"
      }
    }
  }
}
```

## Tools

| Tool | Purpose |
| --- | --- |
| `get_season_context` | Season, phase, cap, and your club |
| `list_teams` | Clubs, division, payroll, cap space, cash, IFA |
| `get_team_roster` | Roster sections used on the team page. Omit the abbreviation for your club |
| `get_roster_compliance` | 40-man and 85-man counts against the limits |
| `search_players` | Name, position, owned, club, level, 30-man and 40-man flags |
| `list_draft_picks` | Picks by year, season, type, or club |
| `list_trades` | Trades, with players and picks on each side |
| `list_transactions` | Posted ledger rows |
| `get_my_wishlist` | Your ranks, tiers, notes, and tags |
| `list_auctions` | Open auctions. Other clubs' bids stay hidden |
| `list_team_ledger` | Payroll, cash, and IFA lines |

`forty_man` counts a player on the 40-man who is not on the end-of-season IL or the foreign list. `reserve` is the 85-man count: everyone except the end-of-season IL, the foreign list, and retired players.

## Deploy

`/mcp` is ASGI. Point the process at:

```bash
uvicorn config.do_app_platform.asgi:application --host 0.0.0.0 --port 8080
```

Locally:

```bash
uvicorn config.dev.asgi:application --host 127.0.0.1 --port 8000
```
