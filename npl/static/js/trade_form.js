(function () {
    var form = document.getElementById("trade-form");
    if (!form) return;

    var PHASE = form.getAttribute("data-phase") || "offseason";
    var LEAGUE_YEAR = Number(form.getAttribute("data-year"));
    var rosterUrl = form.getAttribute("data-roster-url");
    var columnsEl = document.getElementById("trade-columns");
    var poolSection = document.getElementById("trade-pool-section");
    var poolEl = document.getElementById("trade-pool");
    var errorEl = document.getElementById("trade-client-error");
    var dealField = document.getElementById("id_deal");
    var teamField = document.getElementById("id_team");

    var rosters = {};
    var pieces = [];
    var nextId = 1;

    var KINDS = [
        ["player", "Player"],
        ["cap_space", "Cap"],
        ["cash", "Cash"],
        ["ifa_pool", "IFA dollars"],
        ["coverage", "Salary coverage"],
        ["draft_pick", "Draft pick"],
        ["future_considerations", "Player to be named later"]
    ];

    function filingId() {
        return teamField ? String(teamField.value || "") : "";
    }

    function selectedClubs() {
        return Array.prototype.map.call(
            document.querySelectorAll(".trade-club:checked"),
            function (box) { return { id: String(box.value), name: box.parentNode.textContent.trim() }; }
        );
    }

    function clubName(id) {
        var match = selectedClubs().filter(function (club) { return club.id === String(id); })[0];
        return match ? match.name : "";
    }

    function otherClubs(fromId) {
        return selectedClubs().filter(function (club) { return club.id !== String(fromId); });
    }

    function showError(text) {
        errorEl.textContent = text || "";
        errorEl.classList.toggle("hidden", !text);
    }

    function defaultPayer(year, fromId, toId) {
        if (PHASE === "offseason") return String(toId || "");
        if (Number(year) === LEAGUE_YEAR) return String(fromId || "");
        return String(toId || "");
    }

    function percentOf(amount, salary) {
        if (!salary) return 100;
        return Math.max(0, Math.min(100, Math.round(100 * amount / salary)));
    }

    function playerRecord(teamId, playerId) {
        var list = rosters[String(teamId)] || [];
        for (var i = 0; i < list.length; i++) {
            if (String(list[i].id) === String(playerId)) return list[i];
        }
        var ids = Object.keys(rosters);
        for (var t = 0; t < ids.length; t++) {
            list = rosters[ids[t]];
            for (var j = 0; j < list.length; j++) {
                if (String(list[j].id) === String(playerId)) return list[j];
            }
        }
        return null;
    }

    function coverageFromYears(years, fromId, toId) {
        return (years || []).map(function (year) {
            var salary = Number(year.amount || 0);
            return {
                year: Number(year.year),
                salary: salary,
                payers: [{
                    team: defaultPayer(year.year, fromId, toId),
                    percent: 100,
                    amount: salary
                }]
            };
        });
    }

    function applyDefaults(piece) {
        if (piece.kind !== "player" || piece.coverageTouched) return;
        var record = playerRecord(piece.from, piece.player);
        piece.coverage = coverageFromYears(record ? record.years : [], piece.from, piece.to);
    }

    function lockFilingClub() {
        var filing = filingId();
        document.querySelectorAll(".trade-club").forEach(function (box) {
            var isFiling = box.value === filing;
            if (isFiling) {
                box.checked = true;
                box.setAttribute("data-filing", "1");
            } else {
                box.removeAttribute("data-filing");
            }
        });
    }

    function loadRosters() {
        var ids = selectedClubs().map(function (club) { return club.id; }).join(",");
        if (!ids) {
            rosters = {};
            renderColumns();
            return Promise.resolve();
        }
        return fetch(rosterUrl + "?teams=" + encodeURIComponent(ids), { credentials: "same-origin" })
            .then(function (response) { return response.json(); })
            .then(function (payload) {
                rosters = {};
                (payload.teams || []).forEach(function (team) {
                    rosters[String(team.id)] = team.players || [];
                });
                renderColumns();
            })
            .catch(function () {
                showError("The club rosters did not load. Try the clubs again.");
            });
    }

    function renderColumns() {
        var clubs = selectedClubs();
        columnsEl.hidden = clubs.length < 2;
        columnsEl.innerHTML = "";
        clubs.forEach(function (club) {
            var column = document.createElement("div");
            column.className = "trade-column";
            column.setAttribute("data-team", club.id);
            column.innerHTML =
                "<h3 class=\"text-sm font-bold\">" + escapeHtml(club.name) + " sends</h3>" +
                "<label class=\"mt-2 mb-1 block text-xs font-bold\">Piece</label>" +
                "<select class=\"kind w-full\"></select>" +
                "<div class=\"kind-fields mt-2 space-y-2\"></div>" +
                "<button type=\"button\" class=\"btn-line add-piece mt-2\">Add to the pool</button>";
            var kind = column.querySelector(".kind");
            KINDS.forEach(function (pair) {
                var option = document.createElement("option");
                option.value = pair[0];
                option.textContent = pair[1];
                kind.appendChild(option);
            });
            kind.addEventListener("change", function () { renderKindFields(column); });
            renderKindFields(column);
            columnsEl.appendChild(column);
        });
    }

    function renderKindFields(column) {
        var kind = column.querySelector(".kind").value;
        var holder = column.querySelector(".kind-fields");
        var teamId = column.getAttribute("data-team");
        holder.innerHTML = "";
        if (kind === "player") {
            holder.appendChild(playerSelect(teamId, "player"));
        } else if (kind === "coverage") {
            holder.appendChild(label("Player"));
            holder.appendChild(allPlayerSelect());
            holder.appendChild(label("Year"));
            var year = document.createElement("input");
            year.className = "year w-full";
            year.type = "number";
            year.placeholder = "Year";
            holder.appendChild(year);
            holder.appendChild(moneyInput("Dollars"));
        } else if (kind === "cap_space" || kind === "cash" || kind === "ifa_pool") {
            holder.appendChild(moneyInput("Dollars"));
        } else if (kind === "draft_pick") {
            holder.appendChild(textInput("label", "2027 Rule 4, round 1"));
        } else if (kind === "future_considerations") {
            holder.appendChild(textInput("label", "PTBNL"));
        }
    }

    function label(text) {
        var node = document.createElement("label");
        node.className = "mb-1 block text-xs font-bold";
        node.textContent = text;
        return node;
    }

    function playerSelect(teamId, className) {
        var wrap = document.createElement("div");
        wrap.appendChild(label("Player"));
        var select = document.createElement("select");
        select.className = className + " w-full";
        var empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Choose a player";
        select.appendChild(empty);
        (rosters[String(teamId)] || []).forEach(function (player) {
            var option = document.createElement("option");
            option.value = player.id;
            option.textContent = player.name;
            select.appendChild(option);
        });
        wrap.appendChild(select);
        return wrap;
    }

    function allPlayerSelect() {
        var select = document.createElement("select");
        select.className = "player w-full";
        var empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Choose a player";
        select.appendChild(empty);
        selectedClubs().forEach(function (club) {
            (rosters[club.id] || []).forEach(function (player) {
                var option = document.createElement("option");
                option.value = player.id;
                option.textContent = player.name + " (" + club.name + ")";
                option.setAttribute("data-team", club.id);
                select.appendChild(option);
            });
        });
        select.addEventListener("change", function () {
            var record = playerRecord(select.selectedOptions[0] && select.selectedOptions[0].getAttribute("data-team"), select.value);
            var year = select.parentNode.querySelector(".year");
            if (!year || !record || !record.years.length) return;
            year.value = record.years[0].year;
        });
        return select;
    }

    function moneyInput(caption) {
        var wrap = document.createElement("div");
        wrap.appendChild(label(caption));
        var input = document.createElement("input");
        input.className = "amount w-full";
        input.type = "number";
        input.min = "0";
        input.placeholder = "0";
        wrap.appendChild(input);
        return wrap;
    }

    function textInput(className, placeholder) {
        var input = document.createElement("input");
        input.className = className + " w-full";
        input.type = "text";
        input.placeholder = placeholder;
        return input;
    }

    function addPiece(column) {
        var kind = column.querySelector(".kind").value;
        var fromId = column.getAttribute("data-team");
        var others = otherClubs(fromId);
        var toId = others.length === 1 ? others[0].id : "";
        var piece = { id: nextId++, kind: kind, from: fromId, to: toId, coverageTouched: false };
        if (kind === "player") {
            var player = column.querySelector(".player");
            if (!player || !player.value) {
                showError("Choose the player " + clubName(fromId) + " is sending.");
                return;
            }
            piece.player = player.value;
            piece.label = player.selectedOptions[0].textContent;
            applyDefaults(piece);
        } else if (kind === "coverage") {
            var covered = column.querySelector(".player");
            var year = column.querySelector(".year");
            var amount = column.querySelector(".amount");
            if (!covered || !covered.value || !year.value || amount.value === "") {
                showError("Coverage needs a player, a year, and a dollar amount.");
                return;
            }
            var record = playerRecord(covered.selectedOptions[0].getAttribute("data-team"), covered.value);
            var salary = 0;
            if (record) {
                record.years.forEach(function (row) {
                    if (Number(row.year) === Number(year.value)) salary = Number(row.amount || 0);
                });
            }
            var dollars = Number(amount.value);
            if (salary && dollars > salary) {
                showError("That is more than " + record.name + "'s " + year.value + " salary of $" + salary.toLocaleString() + ".");
                return;
            }
            piece.player = covered.value;
            piece.playerTeam = covered.selectedOptions[0].getAttribute("data-team");
            piece.year = Number(year.value);
            piece.amount = dollars;
            piece.salary = salary;
            piece.percent = salary ? percentOf(dollars, salary) : 100;
            piece.label = "Coverage of " + covered.selectedOptions[0].textContent.split(" (")[0] + ", " + year.value;
        } else if (kind === "cap_space" || kind === "cash" || kind === "ifa_pool") {
            var money = column.querySelector(".amount");
            if (!money || money.value === "" || Number(money.value) <= 0) {
                showError("Enter the dollars.");
                return;
            }
            piece.amount = Number(money.value);
        } else if (kind === "draft_pick" || kind === "future_considerations") {
            var label = column.querySelector(".label");
            piece.label = label && label.value.trim();
            if (!piece.label) piece.label = kind === "future_considerations" ? "PTBNL" : "";
            if (kind === "draft_pick" && !piece.label) {
                showError("Describe the pick.");
                return;
            }
        }
        showError("");
        pieces.push(piece);
        renderPool();
    }

    function renderPool() {
        var clubs = selectedClubs();
        poolSection.hidden = pieces.length === 0;
        poolEl.innerHTML = "";
        pieces.forEach(function (piece) {
            var card = document.createElement("article");
            card.className = "border border-gray-300 p-2";
            card.setAttribute("data-id", piece.id);
            var title = document.createElement("p");
            title.className = "text-sm font-bold";
            title.textContent = pieceTitle(piece) + " from " + clubName(piece.from);
            card.appendChild(title);

            var receiverRow = document.createElement("div");
            receiverRow.className = "mt-2";
            receiverRow.appendChild(label(piece.kind === "coverage" ? "Club that is relieved" : "Club that receives it"));
            var receiver = document.createElement("select");
            receiver.className = "receiver w-full max-w-xs";
            var blank = document.createElement("option");
            blank.value = "";
            blank.textContent = "Choose a club";
            receiver.appendChild(blank);
            otherClubs(piece.from).forEach(function (club) {
                var option = document.createElement("option");
                option.value = club.id;
                option.textContent = club.name;
                if (String(piece.to) === club.id) option.selected = true;
                receiver.appendChild(option);
            });
            receiver.addEventListener("change", function () {
                piece.to = receiver.value;
                if (piece.kind === "player") applyDefaults(piece);
                renderPool();
            });
            receiverRow.appendChild(receiver);
            card.appendChild(receiverRow);

            if (piece.kind === "player" && piece.coverage && piece.coverage.length) {
                card.appendChild(coverageEditor(piece));
            } else if (piece.kind === "player") {
                var none = document.createElement("p");
                none.className = "mt-2 text-xs text-gray-600";
                none.textContent = "No contract years are on file for this player.";
                card.appendChild(none);
            }

            var remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn-line remove-piece mt-2";
            remove.textContent = "Remove";
            card.appendChild(remove);
            poolEl.appendChild(card);
        });
        if (clubs.length < 2 && pieces.length) {
            showError("Pick at least one other club.");
        }
    }

    function pieceTitle(piece) {
        if (piece.kind === "player" || piece.kind === "coverage") return piece.label || "Player";
        if (piece.kind === "cap_space") return "Cap $" + Number(piece.amount).toLocaleString();
        if (piece.kind === "cash") return "Cash $" + Number(piece.amount).toLocaleString();
        if (piece.kind === "ifa_pool") return "IFA $" + Number(piece.amount).toLocaleString();
        if (piece.kind === "draft_pick") return piece.label || "Draft pick";
        return piece.label || "Player to be named later";
    }

    function coverageEditor(piece) {
        var wrap = document.createElement("div");
        wrap.className = "mt-2 space-y-2";
        piece.coverage.forEach(function (row) {
            var block = document.createElement("div");
            block.className = "border-t border-gray-200 pt-2";
            var heading = document.createElement("p");
            heading.className = "text-xs font-bold";
            heading.textContent = row.year + " · $" + Number(row.salary || 0).toLocaleString();
            block.appendChild(heading);
            row.payers.forEach(function (payer, index) {
                block.appendChild(payerRow(piece, row, payer, index));
            });
            var split = document.createElement("button");
            split.type = "button";
            split.className = "btn-line mt-1";
            split.textContent = "Split this year";
            split.addEventListener("click", function () {
                piece.coverageTouched = true;
                if (row.payers.length === 1) {
                    var half = Math.floor(Number(row.salary || 0) / 2);
                    row.payers[0].amount = half;
                    row.payers[0].percent = percentOf(half, row.salary);
                    var rest = Number(row.salary || 0) - half;
                    var others = otherClubs(row.payers[0].team);
                    row.payers.push({
                        team: others.length ? others[0].id : "",
                        amount: rest,
                        percent: percentOf(rest, row.salary)
                    });
                } else {
                    row.payers.push({ team: "", amount: 0, percent: 0 });
                }
                renderPool();
            });
            block.appendChild(split);
            wrap.appendChild(block);
        });
        return wrap;
    }

    function payerRow(piece, row, payer, index) {
        var line = document.createElement("div");
        line.className = "mt-1 flex flex-wrap items-center gap-2";
        var select = document.createElement("select");
        select.className = "w-auto";
        var blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "Club";
        select.appendChild(blank);
        selectedClubs().forEach(function (club) {
            var option = document.createElement("option");
            option.value = club.id;
            option.textContent = club.name;
            if (String(payer.team) === club.id) option.selected = true;
            select.appendChild(option);
        });
        select.addEventListener("change", function () {
            piece.coverageTouched = true;
            payer.team = select.value;
        });
        var dollars = document.createElement("input");
        dollars.type = "number";
        dollars.min = "0";
        dollars.max = String(row.salary || "");
        dollars.value = payer.amount;
        dollars.className = "w-28";
        var pct = document.createElement("span");
        pct.className = "text-xs text-gray-600";
        pct.textContent = (row.salary ? percentOf(Number(payer.amount || 0), row.salary) : payer.percent) + "%";
        dollars.addEventListener("input", function () {
            piece.coverageTouched = true;
            var amount = Number(dollars.value || 0);
            if (row.salary && amount > row.salary) {
                amount = row.salary;
                dollars.value = String(amount);
            }
            payer.amount = amount;
            payer.percent = percentOf(amount, row.salary);
            pct.textContent = payer.percent + "%";
        });
        line.appendChild(select);
        line.appendChild(dollars);
        line.appendChild(pct);
        if (row.payers.length > 1) {
            var drop = document.createElement("button");
            drop.type = "button";
            drop.className = "btn-line";
            drop.textContent = "Drop";
            drop.addEventListener("click", function () {
                piece.coverageTouched = true;
                row.payers.splice(index, 1);
                renderPool();
            });
            line.appendChild(drop);
        }
        return line;
    }

    function serialize() {
        return {
            clubs: selectedClubs().map(function (club) { return Number(club.id); }),
            pieces: pieces.map(function (piece) {
                var payload = {
                    kind: piece.kind,
                    from: Number(piece.from),
                    to: piece.to ? Number(piece.to) : "",
                    label: piece.label || ""
                };
                if (piece.player) payload.player = piece.player;
                if (piece.amount != null && piece.kind !== "player") payload.amount = Number(piece.amount);
                if (piece.kind === "coverage") {
                    payload.year = piece.year;
                    payload.percent = piece.percent;
                    payload.salary = piece.salary;
                }
                if (piece.kind === "player") {
                    payload.coverage = (piece.coverage || []).map(function (row) {
                        return {
                            year: row.year,
                            salary: row.salary,
                            payers: row.payers.map(function (payer) {
                                return {
                                    team: payer.team ? Number(payer.team) : "",
                                    percent: Number(payer.percent || 0),
                                    amount: Number(payer.amount || 0),
                                    name: clubName(payer.team)
                                };
                            })
                        };
                    });
                }
                return payload;
            })
        };
    }

    function clientProblems() {
        if (selectedClubs().length < 2) return "A trade needs at least one other club.";
        if (!pieces.length) return "Add at least one piece to the pool.";
        for (var i = 0; i < pieces.length; i++) {
            var piece = pieces[i];
            if (!piece.to) return "Choose the club that receives " + pieceTitle(piece) + ".";
            if (piece.kind === "player" && piece.coverage) {
                for (var y = 0; y < piece.coverage.length; y++) {
                    var row = piece.coverage[y];
                    var total = 0;
                    for (var p = 0; p < row.payers.length; p++) {
                        if (!row.payers[p].team) return row.year + " needs a club covering " + (piece.label || "the player") + ".";
                        total += Number(row.payers[p].amount || 0);
                    }
                    if (row.salary && total !== Number(row.salary)) {
                        return (piece.label || "The player") + "'s " + row.year + " salary is $" + Number(row.salary).toLocaleString() + " and the clubs cover $" + total.toLocaleString() + ".";
                    }
                }
            }
        }
        return "";
    }

    function escapeHtml(text) {
        return String(text).replace(/[&<>"']/g, function (ch) {
            return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[ch];
        });
    }

    function restore(payload) {
        if (!payload || !payload.clubs) return Promise.resolve();
        var wanted = payload.clubs.map(String);
        document.querySelectorAll(".trade-club").forEach(function (box) {
            if (wanted.indexOf(box.value) !== -1) box.checked = true;
        });
        lockFilingClub();
        return loadRosters().then(function () {
            pieces = (payload.pieces || []).map(function (piece) {
                var restored = {
                    id: nextId++,
                    kind: piece.kind,
                    from: String(piece.from),
                    to: piece.to ? String(piece.to) : "",
                    player: piece.player ? String(piece.player) : "",
                    amount: piece.amount,
                    label: piece.label || "",
                    year: piece.year,
                    percent: piece.percent,
                    salary: piece.salary,
                    coverageTouched: true,
                    coverage: (piece.coverage || []).map(function (row) {
                        return {
                            year: row.year,
                            salary: row.salary,
                            payers: (row.payers || []).map(function (payer) {
                                return {
                                    team: payer.team ? String(payer.team) : "",
                                    percent: payer.percent,
                                    amount: payer.amount
                                };
                            })
                        };
                    })
                };
                if (restored.kind === "player" && !restored.label && restored.player) {
                    var record = playerRecord(restored.from, restored.player);
                    restored.label = record ? record.name : restored.player;
                }
                return restored;
            });
            renderPool();
        });
    }

    columnsEl.addEventListener("click", function (event) {
        var button = event.target.closest(".add-piece");
        if (!button) return;
        addPiece(button.closest(".trade-column"));
    });

    poolEl.addEventListener("click", function (event) {
        var button = event.target.closest(".remove-piece");
        if (!button) return;
        var id = Number(button.closest("article").getAttribute("data-id"));
        pieces = pieces.filter(function (piece) { return piece.id !== id; });
        renderPool();
    });

    document.querySelectorAll(".trade-club").forEach(function (box) {
        box.addEventListener("change", function () {
            if (box.getAttribute("data-filing") === "1") box.checked = true;
            var keep = {};
            selectedClubs().forEach(function (club) { keep[club.id] = true; });
            pieces = pieces.filter(function (piece) { return keep[String(piece.from)]; });
            showError("");
            loadRosters().then(renderPool);
        });
    });

    if (teamField) {
        teamField.addEventListener("change", function () {
            lockFilingClub();
            loadRosters().then(renderPool);
        });
    }

    form.addEventListener("submit", function (event) {
        var problem = clientProblems();
        if (problem) {
            event.preventDefault();
            showError(problem);
            return;
        }
        dealField.value = JSON.stringify(serialize());
    });

    lockFilingClub();
    var initialNode = document.getElementById("trade-initial-deal");
    var initial = initialNode ? JSON.parse(initialNode.textContent) : "";
    if (typeof initial === "string" && initial) {
        try { initial = JSON.parse(initial); } catch (err) { initial = null; }
    }
    if (initial && initial.clubs) {
        restore(initial);
    } else if (selectedClubs().length) {
        loadRosters();
    }
})();
