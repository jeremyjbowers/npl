# NPL MCP

Agents can look up rosters, roster limits, players, draft picks, trades, the transaction ledger, open auctions, club finances, and your wishlist. A read-write key can also file a club move on this same server.

A filing is a proposal. The player stays where he is until the league office posts the move. Draft selections and auction bids are not tools. A read-only key can look up the kinds, the proposals, and the open waivers, and it cannot file.

Works with Claude, Codex, GitHub Copilot, Cursor, and any other client that speaks MCP.

## How it works

1. The site serves MCP at `https://YOUR-HOST/mcp` (Streamable HTTP).
2. You authenticate with a long-lived owner API key in the `Authorization: Bearer npl_…` header.
3. The client stores the URL and the key. There is no OAuth step.

The same key works on the JSON API under `/api/mcp/v1/…` if you want to curl the data without MCP. `/api/mcp/v1/` works on the ordinary WSGI site. Remote MCP clients need the ASGI app so `/mcp` is mounted.

## Generate or revoke a key

Sign in and open **API keys** (`/my/api-keys/`).

- **Generate key** creates a read key or a read-write key. A read-write key is the one an agent uses to file a move. The secret stays on that page, so you can copy it later. Only you can see your keys.
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
| `search_players` | Name, position, owned, club, level, 30-man and 40-man flags. `sort=war` ranks by full-season MLB WAR. `offset` pages past the limit |
| `list_free_agents` | Unowned players, best full-season MLB WAR first. `offset` reads the next page |
| `get_player` | One player: contract, WAR, club-split sim lines, and the NPL clubs he has been on |
| `list_draft_picks` | Picks by year, season, type, or club. `held=true` is picks not yet used |
| `list_pick_inventory` | Unused draft picks grouped by the club that holds them |
| `list_trades` | Trades, with the players, draft picks, and cash each club received |
| `list_transactions` | Posted ledger rows, with club names, draft-pick text, and cash |
| `get_my_wishlist` | Your ranks, tiers, notes, and tags |
| `list_auctions` | Open auctions. Other clubs' bids stay hidden |
| `list_team_ledger` | Contract payroll lines, plus cash and IFA adjustments |
| `list_transaction_kinds` | Moves a club can file. Drafts and auction bids are omitted |
| `list_transaction_proposals` | Proposals your club filed or still has to answer. Not the posted ledger |
| `get_transaction_proposal` | One proposal, including the pieces and who has agreed |
| `create_transaction_proposal` | File a nontender, trade, send-down, call-up, release, injured-list move, signing, or waiver request |
| `agree_transaction` | Agree to a proposal waiting on your club |
| `decline_transaction` | Decline a proposal waiting on your club |
| `withdraw_transaction` | Take back a proposal your club filed |
| `list_open_waivers` | Open waivers. This is not an auction |
| `claim_waiver` | Claim a player on an open waiver |

`create_transaction_proposal` acts as the owner of the key. `option_minors` sends a player down. `recall_option` calls him up. `non_tender` nontenders him. Omit `team` when the account owns one club, and pass an abbreviation when it owns more than one. `player` is the mlb_id for a one-player move. A trade passes `counterparty` as the other club's abbreviation. A deal with several pieces passes `assets`, and each piece's `from_team` and `to_team` is an abbreviation or an id. `list_transactions` is the posted ledger. `list_transaction_proposals` is what has been filed and not yet posted.

WAR on a player is his full MLB season. It is not the portion he played for one NPL club. `npl_lines` are the simulated counting stats already split by NPL club. `get_player` lists the clubs and the dates. The service does not prorate MLB WAR across those stints.

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
