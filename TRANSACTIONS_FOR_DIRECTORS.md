# Transactions on the NPL site

A briefing for directors on how clubs submit transactions, and how you review them.

This describes the transaction tools in the current site update. Clubs file a **proposal**. You inspect it, send it back if something is wrong, and still apply the roster effect yourselves. The public transaction log is the historical record. Filing a proposal does not, by itself, move a player, a contract, or a draft pick.

## What changed

A club submission used to be a form dropped in a pile. It is now a proposal with three parts:

- **Who filed it**, and which club it belongs to.
- **Who else is involved.** A trade names the other club and waits until that club agrees. A roster move, signing, or waiver does not need a second club.
- **What changes hands.** Each piece in a trade names the club that gives it and the club that gets it. Under rule 8.7.1 a piece can be a player under contract, a player to be named later, cash, carried salary, a draft pick for the next draft, or IFA cap space. Signings also carry the contract terms (years, dollars, points).

The same proposal is what you see in the admin, what the club sees under My Submissions, and what an agent sees if the club is using the API.

Clubs can still only file for a club they own. A club marked frozen (unpaid or vacant) cannot file. The site tells clubs that transactions are processed Mondays at 1 PM EST.

## How a club files

From the site, a signed-in owner uses **Transactions → Submit Transaction**, picks a type, and fills in the details. They can follow it under **Transactions → My Submissions**.

The form covers:

- Trades. Any number of clubs can be in one trade. The filing is the list of pieces, and each piece says who gives it and who gets it.
- Signings: offseason MLB (points), in-season free agent (dollars, one year), minor-league contract, extension, and IFA
- Offseason transactions
- Injured list (7-day, 56-day, end of season, COVID, a move between lists, and activation)
- Option to the minors, recall, and purchase of a contract
- Release
- Waiver request (outright, trade, or Rule 5) and waiver claim
- In limbo assignment
- Restricted list, including the list type (restricted, domestic violence, PED, betting, paternity, family medical, bereavement, or pending a suspension)
- Foreign list, retirement, and death

A trade stays **Awaiting agreement** until every other club in the deal agrees, or one of them declines. A two-club trade and a trade among more clubs work the same way: the clubs are whoever gives or gets a piece. Everyone else lands as **Proposed** and waits for the Monday window.

A club can withdraw its own proposal while it is still open. The other club can decline a trade. A declined trade is **Rejected**. A withdrawn one is **Withdrawn**.

## What you review

Staff see **Transactions → Review proposals**, which opens the proposal list in the admin. Each proposal shows the club, the kind of transaction, the status, who submitted it, and when.

Open a proposal to see:

- The clubs involved, and whether the other club has agreed
- Each asset (player, pick, cash, IFA space, and so on)
- Notes and contract terms

If the filing is improper, check **Flagged** under Director review and write what the club needs to change. The note is required. The club then sees a **Needs a fix** tag and your note on My Submissions. Clear the flag once the filing is acceptable. The list can be filtered to flagged proposals.

You can also search by club, kind, or the text of a note.

## What a club sees before Monday

Until a proposal is processed, the roster and the books stay official. The site now shows the pending overlay so an owner is not guessing.

- A player in an open trade, release, non-tender, waiver, retirement, or foreign-list filing is grey on the club page, with a link to that proposal.
- Under cap space, cash, and IFA pool space, a grey line shows the figure if those open proposals clear.
- The same grey money line appears on the team cards on the home page.

The proposal itself says it has not been processed.

## Filings the site turns away

A proposal is rejected, with a reason, when it cannot be true on the current roster:

- The player is not on that club, or a signing names a player who already has a club.
- An option names someone off the 40-man, already on option, or out of options on the active roster (rules 8.3.1 and 8.3.3). A recall names someone who is not on option. A contract purchase names someone already on the 40-man.
- The same player is already in another proposal that has not been processed.
- The filing would put the club over 40 players on the 40-man, counting other open proposals.
- The filing would spend cash or IFA pool space the club does not have, again counting other open proposals (rules 8.7.5.1 and 8.7.4).

Section 8 of the rules also blocks a filing before it is stored, and the message names the section:

- Injured-list placement in the offseason, a backdated IL date, or a 56-day IL when the 40-man is not full (8.2, 8.2.1).
- An option in September or the offseason, or of a player who is on the injured list (8.3.2.1, 8.2).
- A nontender during the season (8.4.2).
- A major-league contract traded in the postseason (8.7.2). Directors set that phase when the July 31 deadline passes, and move back to the offseason after the World Series.
- A draft pick more than one draft ahead, or a 40-man player named as the player to be named later (8.7.1). Cap space, cash, IFA dollars, and coverage of a named player's salary can be traded. Coverage of one year cannot go past that year's salary.
- Outright waivers for a player who is not on the 40-man (8.8.2.1).
- A minor-league player placed on the foreign list (8.1.2).

A release that frees a known salary adds that salary back to cap space in the preview. A signing subtracts its total. Cash, cap space, IFA pool space, and salary coverage move with those assets. On a traded player, the sending club covers the current year during the season and the receiving club covers the later years. In the offseason the receiving club covers every year, unless the clubs split a year. Directors still decide the close calls the roster data cannot see, including whether an injury is real, whether a contract is guaranteed, and whether the World Series is over.

Directors set the phase on the current season in the admin. The rules name three phases: offseason, regular season, and postseason. Spring training, roster freezes, Winter Meetings, and the October quiet period sit inside those phases. They are not separate settings.

## What you still do yourselves

The proposal is the filing. It is not the roster move.

- You still apply the player, contract, and draft-pick effects.
- **Transactions → All Transactions** is the public historical log. It is separate from the proposal list.
- The software can record an approved proposal onto that log, but there is not yet a button for it. Until that exists, the log and the sheet remain how a processed transaction is published.
- Labels from the 2025 and 2026 transaction sheets (for example “IL: 7 Day”, “Waiver Request: Outright”, “R5 Draft Pick”) have a standard name in the new list, so older sheet language and new filings refer to the same kinds of moves.

## Waivers and drafts

A waiver request opens a waiver on that player. Another club claims it from the waiver-claim form, or through the API. The club that placed the waiver cannot claim it. Each club can have one claim on a given waiver.

A draft pick filed while a Rule 4 or Rule 5 draft is on the clock is stored as a proposal. It names the player for the current pick. It does not move that player onto the club until you post the selection.

## Agents and API tokens

A club may let an agent file and read transactions for them. The owner creates the credential under **Transactions → API tokens**.

There are two choices:

- **Read.** The agent can look up transaction types, that club’s proposals, and drafts.
- **Read and write.** The agent can also file, agree, decline, withdraw, claim a waiver, and submit a draft pick.

The token acts as that owner. It can only see and file for that owner’s clubs. The secret is shown once, when it is created. The owner can revoke it on that same page. Revocation is immediate.

In the admin, under API tokens, you can see the label, the owner, whether it is read or read-write, when it was created, and when it was last used. You cannot see the secret. You can revoke a token from that screen if one should be shut off.

A person using the site in the browser does not need a token. The token is only for an agent calling the site on the owner’s behalf.
