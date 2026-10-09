"""MCP tool manifest for the transaction service.

An MCP server can advertise these tools and forward each call to the matching
function in npl.transactions.service. The HTTP API under /api/v1/ is the same
surface. This module does not depend on an MCP library.
"""

from npl.transactions.catalog import ASSET_TYPES, KINDS

_KIND_CODES = sorted(KINDS)


def tool_manifest():
    asset_schema = {
        "type": "object",
        "properties": {
            "asset_type": {"type": "string", "enum": list(ASSET_TYPES)},
            "player": {"type": "string", "description": "Player mlb_id"},
            "raw_label": {"type": "string"},
            "mlb_id": {"type": "string"},
            "scoresheet_id": {"type": "string"},
            "from_team": {"type": "integer"},
            "to_team": {"type": "integer"},
            "amount": {"type": "integer", "description": "Dollars"},
            "draft_pick": {"type": "integer"},
            "contract_terms": {"type": "object"},
            "notes": {"type": "string"},
        },
    }
    return [
        {
            "name": "list_transaction_kinds",
            "description": "List canonical NPL transaction kinds, including which ones need another team's agreement or contract terms.",
            "method": "GET",
            "path": "/api/v1/transactions/kinds/",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_transaction_proposals",
            "description": "List transaction proposals that involve one of the signed-in manager's teams.",
            "method": "GET",
            "path": "/api/v1/transactions/proposals/",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "create_transaction_proposal",
            "description": "Propose a trade, signing, waiver, roster move, or other transaction. Trades stay open until the other team agrees.",
            "method": "POST",
            "path": "/api/v1/transactions/proposals/",
            "input_schema": {
                "type": "object",
                "required": ["team", "code"],
                "properties": {
                    "team": {"type": "integer"},
                    "code": {"type": "string", "enum": _KIND_CODES},
                    "counterparty_team": {"type": "integer"},
                    "notes": {"type": "string"},
                    "effective_date": {"type": "string", "format": "date"},
                    "contract_terms": {"type": "object"},
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
            "description": "Fetch one proposal, including parties, assets, and waiver id.",
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
            "description": "Agree to a trade proposal on behalf of the counterparty team.",
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
            "description": "Decline a trade proposal.",
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
            "description": "Withdraw a proposal your team submitted.",
            "method": "POST",
            "path": "/api/v1/transactions/proposals/{id}/withdraw/",
            "input_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
        },
        {
            "name": "claim_waiver",
            "description": "Claim a player on an open outright, trade, or Rule 5 waiver.",
            "method": "POST",
            "path": "/api/v1/waivers/{id}/claim/",
            "input_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
                    "notes": {"type": "string"},
                },
            },
        },
        {
            "name": "list_drafts",
            "description": "List Rule 4, Rule 5, and in-season draft sessions.",
            "method": "GET",
            "path": "/api/v1/drafts/",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "submit_draft_pick",
            "description": "Submit the player for the pick currently on the clock. The selection is stored as a proposal and does not move the player until directors post it.",
            "method": "POST",
            "path": "/api/v1/drafts/{id}/pick/",
            "input_schema": {
                "type": "object",
                "required": ["id", "player"],
                "properties": {
                    "id": {"type": "integer"},
                    "player": {"type": "string", "description": "Player mlb_id"},
                },
            },
        },
    ]
