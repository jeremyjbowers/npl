"""Tool manifest for the transaction API.

The league MCP server itself lives in npl.mcp_app and is served at /mcp.
These names match that server. Callers authenticate with Authorization: Bearer
and a key from /my/api-keys/. Read keys can list. Read-write keys can file
a club move. Draft selections and auction bids are not tools here.
"""

from npl.transactions.catalog import ASSET_TYPES, fileable_kinds

_FILEABLE_CODES = sorted(kind["code"] for kind in fileable_kinds())


def tool_manifest():
    asset_schema = {
        "type": "object",
        "properties": {
            "asset_type": {"type": "string", "enum": list(ASSET_TYPES)},
            "player": {"type": "string", "description": "Player mlb_id"},
            "raw_label": {"type": "string"},
            "mlb_id": {"type": "string"},
            "scoresheet_id": {"type": "string"},
            "from_team": {"type": "string", "description": "Club id or abbreviation"},
            "to_team": {"type": "string", "description": "Club id or abbreviation"},
            "amount": {"type": "integer", "description": "Dollars"},
            "draft_pick": {"type": "integer"},
            "contract_terms": {"type": "object"},
            "notes": {"type": "string"},
        },
    }
    return [
        {
            "name": "list_transaction_kinds",
            "description": (
                "Codes a club can file, including a nontender, a trade, "
                "option_minors (send down), and recall_option (call up). "
                "Draft selections and auction bids are not listed."
            ),
            "method": "GET",
            "path": "/api/v1/transactions/kinds/?fileable=1",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_transaction_proposals",
            "description": "Proposals your clubs have filed or been asked to agree to. This is not the posted ledger.",
            "method": "GET",
            "path": "/api/v1/transactions/proposals/",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "create_transaction_proposal",
            "description": (
                "File a move for your club. player is the mlb_id for a one-player move. "
                "Omit team when the account owns one club. A trade needs counterparty_team. "
                "Draft selections and auction bids are refused. The filing is a proposal "
                "and does not move the player until the league office posts it."
            ),
            "method": "POST",
            "path": "/api/v1/transactions/proposals/",
            "input_schema": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "team": {
                        "type": "string",
                        "description": "Club id or abbreviation. Omit when the account owns one club.",
                    },
                    "code": {"type": "string", "enum": _FILEABLE_CODES},
                    "player": {
                        "type": "string",
                        "description": "mlb_id for a one-player move such as a nontender, option, recall, or release.",
                    },
                    "counterparty_team": {
                        "type": "string",
                        "description": "The other club's id or abbreviation.",
                    },
                    "counterparty_teams": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Other clubs in a trade. Clubs are also taken from each asset.",
                    },
                    "notes": {"type": "string"},
                    "effective_date": {"type": "string", "format": "date"},
                    "contract_terms": {"type": "object"},
                    "amount": {"type": "integer", "description": "Dollars, for a signing."},
                    "assets": {"type": "array", "items": asset_schema},
                    "veteran_disposition": {
                        "type": "string",
                        "enum": ["", "keep_40", "release"],
                    },
                },
            },
        },
        {
            "name": "get_transaction_proposal",
            "description": "Fetch one proposal your club is party to, including assets and who still has to agree.",
            "method": "GET",
            "path": "/api/v1/transactions/proposals/{id}/",
            "input_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
        },
        {
            "name": "agree_transaction",
            "description": "Agree to a proposal waiting on your club. The player stays put until the league office posts the move.",
            "method": "POST",
            "path": "/api/v1/transactions/proposals/{id}/agree/",
            "input_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
        },
        {
            "name": "decline_transaction",
            "description": "Decline a proposal waiting on your club.",
            "method": "POST",
            "path": "/api/v1/transactions/proposals/{id}/decline/",
            "input_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
        },
        {
            "name": "withdraw_transaction",
            "description": "Withdraw a proposal your club filed.",
            "method": "POST",
            "path": "/api/v1/transactions/proposals/{id}/withdraw/",
            "input_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
        },
        {
            "name": "list_open_waivers",
            "description": "Open waivers a club can claim. This is not an auction.",
            "method": "GET",
            "path": "/api/v1/waivers/",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "claim_waiver",
            "description": "Claim a player on an open waiver. This is not an auction bid. The league office still posts the move.",
            "method": "POST",
            "path": "/api/v1/waivers/{id}/claim/",
            "input_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
                    "team": {"type": "string", "description": "Club id or abbreviation. Omit when the account owns one other club."},
                    "notes": {"type": "string"},
                },
            },
        },
    ]
