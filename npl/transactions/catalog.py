"""Canonical NPL transaction kinds.

Sheet labels from the 2025 and 2026 transaction logs are aliases. The rules
chapters (contracts, amateur acquisition, free agency, transaction types) and
the other workbook tabs (waivers, Rule 4, Rule 5, IL, restricted list, free
agents) decide which fields each kind carries.
"""

ASSET_PLAYER = "player"
ASSET_DRAFT_PICK = "draft_pick"
ASSET_CASH = "cash"
ASSET_IFA = "ifa_pool"
ASSET_CARRIED_SALARY = "carried_salary"
ASSET_FUTURE = "future_considerations"

ASSET_TYPES = (
    ASSET_PLAYER,
    ASSET_DRAFT_PICK,
    ASSET_CASH,
    ASSET_IFA,
    ASSET_CARRIED_SALARY,
    ASSET_FUTURE,
)

# Categories used by the catalog. Auction results stay on /auctions/;
# the kind exists so the category is addressable from the API.
CATEGORIES = ("roster", "contract", "waiver", "trade", "auction", "draft")

SHEET_ASSET_LABELS = {
    "cash reserves": ASSET_CASH,
    "cash": ASSET_CASH,
    "cash considerations": ASSET_CASH,
    "ifa cap space": ASSET_IFA,
    "ifa": ASSET_IFA,
    "ifa pool $": ASSET_IFA,
    "ifa pool space": ASSET_IFA,
    "draft pick": ASSET_DRAFT_PICK,
    "r5 draft pick": ASSET_DRAFT_PICK,
    "future considerations": ASSET_FUTURE,
    "ptbnl": ASSET_FUTURE,
    "player to be named later": ASSET_FUTURE,
    "carried salary": ASSET_CARRIED_SALARY,
    "carried salary obligation": ASSET_CARRIED_SALARY,
}

# code, label, category, agreement, contract terms, manager-initiable
_KIND_ROWS = (
    ("il_7", "IL: 7 Day", "roster", False, False, True),
    ("il_56", "IL: 56 Day", "roster", False, False, True),
    ("il_eos", "IL: End of Season", "roster", False, False, True),
    ("il_activate", "IL: Activate", "roster", False, False, True),
    ("option_minors", "Option to Minors", "roster", False, False, True),
    ("recall_option", "Recall Option", "roster", False, False, True),
    ("purchase_contract", "Contract: Purchased", "roster", False, True, True),
    ("release", "Release", "roster", False, False, True),
    ("non_tender", "Non-Tender", "contract", False, False, True),
    ("restricted_place", "Restricted List", "roster", False, False, True),
    ("restricted_activate", "Restricted List: Activate", "roster", False, False, True),
    ("foreign_place", "Foreign List", "roster", False, False, True),
    ("foreign_reinstate", "Reinstate: Foreign List", "roster", False, False, True),
    ("retirement", "Retirement", "roster", False, False, True),
    ("death", "Death", "roster", False, False, True),
    ("mlb_signing", "MLB Signing", "contract", False, True, True),
    ("in_season_fa", "In Season FA", "contract", False, True, True),
    ("minor_signing", "Minor League Signing", "contract", False, True, True),
    ("ifa_signing", "IFA Signing", "contract", False, True, True),
    ("extension", "Extension", "contract", False, True, True),
    ("exercise_option", "Exercise Option", "contract", False, True, True),
    ("exercise_vesting_option", "Exercise Vesting Option", "contract", False, True, True),
    ("decline_option", "Decline Option", "contract", False, True, True),
    ("qualifying_offer", "Qualifying Offer", "contract", False, True, True),
    ("contract_amnesty", "Contract Amnesty", "contract", False, False, True),
    ("waiver_request_outright", "Waiver Request: Outright", "waiver", False, False, True),
    ("waiver_request_trade", "Waiver Request: Trade", "waiver", False, False, True),
    ("waiver_cleared_outright", "Cleared: OR Waivers", "waiver", False, False, False),
    ("waiver_claimed", "Claimed: OR Waivers", "waiver", False, False, True),
    ("waiver_request_rule5", "Rule 5 Waiver Request", "waiver", False, False, True),
    ("waiver_returned_rule5", "Returned: Rule 5 Waivers", "waiver", False, False, False),
    ("rule5_draft", "Rule 5 Draft", "draft", False, False, False),
    ("rule4_draft", "Rule 4 Draft", "draft", False, True, False),
    ("auction_result", "Auction Result", "auction", False, True, False),
    ("trade", "Trade", "trade", True, False, True),
)

KINDS = {
    code: {
        "code": code,
        "label": label,
        "category": category,
        "requires_agreement": agreement,
        "requires_contract": contract,
        "manager_can_initiate": initiate,
    }
    for code, label, category, agreement, contract, initiate in _KIND_ROWS
}

# Lowercased labels from the 2025 and 2026 transaction tabs.
SHEET_ALIASES = {
    "trade": "trade",
    "option to aaa": "option_minors",
    "option to minors": "option_minors",
    "release": "release",
    "il: 7 day": "il_7",
    "recall option": "recall_option",
    "il: activate": "il_activate",
    "activate": "il_activate",
    "contract: purchased": "purchase_contract",
    "contract purchased": "purchase_contract",
    "mlb signing": "mlb_signing",
    "contract: mlb signing": "mlb_signing",
    "free agent signing": "mlb_signing",
    "non-tender": "non_tender",
    "nontender": "non_tender",
    "cleared: or waivers": "waiver_cleared_outright",
    "waivers: cleared": "waiver_cleared_outright",
    "in season fa": "in_season_fa",
    "ifa signing": "ifa_signing",
    "waiver request: outright": "waiver_request_outright",
    "outright waivers": "waiver_request_outright",
    "il: 56 day": "il_56",
    "56 day il": "il_56",
    "minor league signing": "minor_signing",
    "minors signing": "minor_signing",
    "il: eos": "il_eos",
    "eos il": "il_eos",
    "il: end of season": "il_eos",
    "claimed: or waivers": "waiver_claimed",
    "waiver claim": "waiver_claimed",
    "waivers: claimed": "waiver_claimed",
    "waivers claim": "waiver_claimed",
    "waiver request: claim": "waiver_claimed",
    "extension": "extension",
    "contract: extension": "extension",
    "qualifying offer": "qualifying_offer",
    "contract: qualifying offer": "qualifying_offer",
    "decline option": "decline_option",
    "contract: decline option": "decline_option",
    "option declined": "decline_option",
    "restricted list": "restricted_place",
    "restricted list: place": "restricted_place",
    "foreign list": "foreign_place",
    "exercise option": "exercise_option",
    "contract: exercise option": "exercise_option",
    "contract: exercise vesting option": "exercise_vesting_option",
    "contract amnesty": "contract_amnesty",
    "rl: activate": "restricted_activate",
    "restricted list - activate": "restricted_activate",
    "restricted list: activate": "restricted_activate",
    "rule 5 waiver request": "waiver_request_rule5",
    "waiver request: rule 5": "waiver_request_rule5",
    "waivers: rule 5": "waiver_request_rule5",
    "reinstate: foreign list": "foreign_reinstate",
    "retirement": "retirement",
    "returned: rule 5 waivers": "waiver_returned_rule5",
    "r5 waiver request: cleared/returned": "waiver_returned_rule5",
    "r5 waiver request: cleared": "waiver_returned_rule5",
    "r5 waiver request: returned": "waiver_returned_rule5",
    "rule 5 draft": "rule5_draft",
    "death": "death",
}

FORM_TYPE_TO_CODE = {
    "injured_list": "il_7",
    "option_minors": "option_minors",
    "purchase_contract": "purchase_contract",
    "recall_option": "recall_option",
    "release_player": "release",
    "waiver_request": "waiver_request_outright",
    "waiver_claim": "waiver_claimed",
    "restricted_list": "restricted_place",
    "limbo_assignment": "restricted_place",
}

IL_FORM_TO_CODE = {
    "7-day": "il_7",
    "56-day": "il_56",
    "60-day": "il_56",
    "15-day": "il_7",
    "eos": "il_eos",
}

WAIVER_FORM_TO_CODE = {
    "outright": "waiver_request_outright",
    "trade": "waiver_request_trade",
    "release": "release",
    "rule5": "waiver_request_rule5",
}

OFFSEASON_FORM_TO_CODE = {
    "signing": "mlb_signing",
    "trade": "trade",
    "extension": "extension",
    "minor_league_contract": "minor_signing",
    "invitation": "minor_signing",
    "other": "mlb_signing",
}

FOREIGN_FORM_TO_CODE = {
    "foreign": "foreign_place",
    "retirement": "retirement",
    "death": "death",
}

SIGNING_CODES = ("mlb_signing", "in_season_fa", "minor_signing", "ifa_signing", "extension")


def get_kind(code):
    try:
        return KINDS[code]
    except KeyError:
        raise KeyError(f"Unknown transaction kind: {code}")


def normalize_sheet_type(raw):
    """Map a transaction-log label to a canonical code, or None if it is noise."""
    if raw is None:
        return None
    key = " ".join(str(raw).strip().lower().split())
    if not key or key == "ss":
        return None
    if key in KINDS:
        return key
    return SHEET_ALIASES.get(key)


def sheet_asset_type(player_cell):
    if not player_cell:
        return None
    key = " ".join(str(player_cell).strip().lower().split())
    return SHEET_ASSET_LABELS.get(key)


def manager_kinds():
    return [kind for kind in KINDS.values() if kind["manager_can_initiate"]]


def kinds_by_category():
    grouped = {}
    for kind in KINDS.values():
        grouped.setdefault(kind["category"], []).append(kind)
    return grouped
