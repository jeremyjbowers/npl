// ABOUTME: Stateless JSON routes for the engine: start, step, matchup, pitcher, substitute, positions, and health.
// ABOUTME: Every request carries the whole game state; the process keeps nothing between requests.
//! The engine's HTTP surface.
//!
//! `POST /start` opens a fixture with a seed. `POST /step` resolves exactly one plate
//! appearance from a state, an optional call, a seed, and optional runner ratings
//! (`runners` keyed by base, and `league_spd`). The call `none` plays the plate appearance
//! with no call at all, where an omitted call lets the computer manager decide.
//! `POST /matchup` reports the outcome probabilities the next plate appearance will draw
//! from. `POST /pitcher` makes a pitching change for the fielding club from a card and a
//! seed. `POST /substitute` puts a batter card in one batting-order slot, with an optional
//! `role`: `pinch_hitter`, `pinch_runner`, `defense`, or the default `replacement`.
//! `POST /positions` gives the fielding club's players new positions. `GET /health` answers
//! App Platform. The caller holds the state. The same state, call, and seed give the same result.

use axum::body::Bytes;
use axum::extract::DefaultBodyLimit;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::de::DeserializeOwned;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::game::{Game, GameError, PositionChange, SubstituteRole};
use crate::model::{BaseRunners, BatterCard, GameFixture, PitcherCard, PrePaCalls, Running, Side};
use crate::service::{self, Matchup, Stepped};

/// A finished extra-inning game is a few hundred kilobytes. This leaves room without being unbounded.
const BODY_LIMIT_BYTES: usize = 16 * 1024 * 1024;

pub fn router() -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/start", post(start))
        .route("/step", post(step))
        .route("/matchup", post(matchup))
        .route("/pitcher", post(pitcher))
        .route("/substitute", post(substitute))
        .route("/positions", post(positions))
        .layer(DefaultBodyLimit::max(BODY_LIMIT_BYTES))
}

#[derive(Deserialize)]
struct StartRequest {
    fixture: GameFixture,
    seed: u64,
}

#[derive(Deserialize)]
struct StepRequest {
    state: Game,
    #[serde(default)]
    call: Option<String>,
    seed: u64,
    /// Ratings of the runners on base. Omitted, every runner runs at the league constants.
    #[serde(default)]
    runners: BaseRunners,
    #[serde(default)]
    league_spd: Option<f64>,
}

#[derive(Deserialize)]
struct PitcherRequest {
    state: Game,
    pitcher: PitcherCard,
    seed: u64,
}

#[derive(Deserialize)]
struct SubstituteRequest {
    state: Game,
    side: Side,
    index: usize,
    batter: BatterCard,
    /// Omitted, a plain replacement at the same position, as before roles existed.
    #[serde(default)]
    role: SubstituteRole,
}

#[derive(Deserialize)]
struct PositionsRequest {
    state: Game,
    side: Side,
    changes: Vec<PositionChange>,
}

#[derive(Deserialize)]
struct MatchupRequest {
    state: Game,
}

async fn health() -> Json<Value> {
    Json(json!({ "status": "ok" }))
}

async fn start(body: Bytes) -> Result<Json<Value>, HttpError> {
    let request: StartRequest = parse(&body)?;
    let game = service::start(request.fixture, request.seed).map_err(HttpError::Game)?;
    Ok(Json(json!({ "state": game })))
}

async fn step(body: Bytes) -> Result<Json<Stepped>, HttpError> {
    let request: StepRequest = parse(&body)?;
    let call = match request.call.as_deref() {
        None => None,
        Some(name) => Some(named_call(name)?),
    };
    let running = Running {
        runners: request.runners,
        league_spd: request.league_spd,
    };
    service::step(request.state, call, request.seed, &running)
        .map(Json)
        .map_err(HttpError::Game)
}

async fn matchup(body: Bytes) -> Result<Json<Matchup>, HttpError> {
    let request: MatchupRequest = parse(&body)?;
    service::matchup(&request.state)
        .map(Json)
        .map_err(HttpError::Game)
}

async fn pitcher(body: Bytes) -> Result<Json<Value>, HttpError> {
    let request: PitcherRequest = parse(&body)?;
    let game = service::bring_in_pitcher(request.state, request.pitcher, request.seed)
        .map_err(HttpError::Game)?;
    Ok(Json(json!({ "state": game })))
}

async fn substitute(body: Bytes) -> Result<Json<Value>, HttpError> {
    let request: SubstituteRequest = parse(&body)?;
    let game = service::substitute(
        request.state,
        request.side,
        request.index,
        request.batter,
        request.role,
    )
    .map_err(HttpError::Game)?;
    Ok(Json(json!({ "state": game })))
}

async fn positions(body: Bytes) -> Result<Json<Value>, HttpError> {
    let request: PositionsRequest = parse(&body)?;
    let game = service::set_positions(request.state, request.side, request.changes)
        .map_err(HttpError::Game)?;
    Ok(Json(json!({ "state": game })))
}

fn parse<T: DeserializeOwned>(body: &[u8]) -> Result<T, HttpError> {
    serde_json::from_slice(body).map_err(|err| HttpError::BadRequest(err.to_string()))
}

fn named_call(name: &str) -> Result<PrePaCalls, HttpError> {
    let mut calls = PrePaCalls::default();
    match name {
        "none" => {}
        "bunt" => calls.bunt = true,
        "intentional_walk" => calls.intentional_walk = true,
        "steal" => calls.steal = true,
        "hit_and_run" => calls.hit_and_run = true,
        "infield_in" => calls.infield_in = true,
        _ => return Err(HttpError::BadCall),
    }
    Ok(calls)
}

enum HttpError {
    Game(GameError),
    BadRequest(String),
    BadCall,
}

impl IntoResponse for HttpError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            Self::Game(GameError::GameOver) => (
                StatusCode::CONFLICT,
                "The game is final. There is no next plate appearance.".to_string(),
            ),
            Self::Game(err) => (StatusCode::UNPROCESSABLE_ENTITY, err.to_string()),
            Self::BadRequest(message) => (StatusCode::BAD_REQUEST, message),
            Self::BadCall => (
                StatusCode::BAD_REQUEST,
                "The call must be none, bunt, intentional_walk, steal, hit_and_run, infield_in, or omitted."
                    .to_string(),
            ),
        };
        (status, Json(json!({ "error": message }))).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use http_body_util::BodyExt;
    use serde_json::{json, Value};
    use tower::ServiceExt;

    use crate::game::Game;
    use crate::model::{load_json, GameFixture, PlateOutcome};

    fn fixture() -> GameFixture {
        let path = format!("{}/fixtures/game.json", env!("CARGO_MANIFEST_DIR"));
        load_json(&path).expect("fixture")
    }

    async fn exchange(request: Request<Body>) -> (StatusCode, Value) {
        let response = router().oneshot(request).await.expect("engine response");
        let status = response.status();
        let bytes = response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes();
        let value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
        (status, value)
    }

    async fn post(uri: &str, body: Value) -> (StatusCode, Value) {
        exchange(
            Request::builder()
                .method("POST")
                .uri(uri)
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
    }

    async fn started(seed: u64) -> Value {
        let (status, body) = post("/start", json!({ "fixture": fixture(), "seed": seed })).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        body["state"].clone()
    }

    fn game(state: &Value) -> Game {
        serde_json::from_value(state.clone()).expect("game state")
    }

    #[tokio::test]
    async fn health_answers() {
        let (status, body) = exchange(
            Request::builder()
                .uri("/health")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["status"], "ok");
    }

    #[tokio::test]
    async fn start_returns_the_opening_state() {
        let state = started(7).await;
        let opening = game(&state);
        assert_eq!(opening.inning, 1);
        assert_eq!(opening.outs, 0);
        assert!(opening.results.is_empty());
        assert!(opening.home.pitcher_slot.is_some());
        assert_eq!(
            started(7).await,
            state,
            "the same seed opened a different game"
        );
    }

    #[tokio::test]
    async fn start_rejects_a_missing_seed() {
        let (status, body) = post("/start", json!({ "fixture": fixture() })).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(body["error"].as_str().unwrap().contains("seed"));
    }

    #[tokio::test]
    async fn two_steps_follow_one_another() {
        let state = started(1).await;
        let (status, first) = post("/step", json!({ "state": state, "seed": 11 })).await;
        assert_eq!(status, StatusCode::OK, "{first}");
        let after_first = game(&first["state"]);
        assert_eq!(after_first.results.len(), 1);
        assert_eq!(
            serde_json::to_value(&after_first.results[0]).unwrap(),
            first["result"]
        );

        let (status, second) = post(
            "/step",
            json!({ "state": first["state"], "call": null, "seed": 12 }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{second}");
        let after_second = game(&second["state"]);
        assert_eq!(after_second.results.len(), 2);
        assert_eq!(
            after_second.results[0], after_first.results[0],
            "the first plate appearance was played again"
        );
        assert_ne!(
            after_second.results[1].batter_id, after_second.results[0].batter_id,
            "the second step did not advance the batting order"
        );
    }

    #[tokio::test]
    async fn the_same_state_call_and_seed_give_the_same_result() {
        let state = started(3).await;
        let request = json!({ "state": state, "call": "hit_and_run", "seed": 99 });
        let (_, one) = post("/step", request.clone()).await;
        let (_, two) = post("/step", request).await;
        assert_eq!(one, two);

        let mut seeds_differ = false;
        for seed in 0..20u64 {
            let (_, other) = post("/step", json!({ "state": state, "seed": seed })).await;
            if other["result"] != one["result"] {
                seeds_differ = true;
                break;
            }
        }
        assert!(seeds_differ, "the seed does not reach the draw");
    }

    #[tokio::test]
    async fn a_whole_game_plays_through_the_step_route() {
        let mut state = started(5).await;
        let mut steps = 0u64;
        while !game(&state).is_final() {
            steps += 1;
            assert!(steps < 2_000, "the game did not end");
            let (status, body) = post("/step", json!({ "state": state, "seed": steps })).await;
            assert_eq!(status, StatusCode::OK, "{body}");
            state = body["state"].clone();
        }
        let (status, body) = post("/step", json!({ "state": state, "seed": 0 })).await;
        assert_eq!(status, StatusCode::CONFLICT);
        assert!(body["error"].as_str().unwrap().contains("final"));
    }

    #[tokio::test]
    async fn an_intentional_walk_is_honored() {
        let state = started(2).await;
        let (status, body) = post(
            "/step",
            json!({ "state": state, "call": "intentional_walk", "seed": 4 }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let outcome: PlateOutcome =
            serde_json::from_value(body["result"]["outcome"].clone()).unwrap();
        assert_eq!(outcome, PlateOutcome::IntentionalWalk);
    }

    #[tokio::test]
    async fn a_bunt_is_honored() {
        let state = started(2).await;
        let (status, body) = post(
            "/step",
            json!({ "state": state, "call": "bunt", "seed": 4 }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let outcome: PlateOutcome =
            serde_json::from_value(body["result"]["outcome"].clone()).unwrap();
        assert!(matches!(
            outcome,
            PlateOutcome::BuntSingle | PlateOutcome::BuntSacrifice | PlateOutcome::BuntOut
        ));
    }

    #[tokio::test]
    async fn a_steal_with_a_runner_on_first_is_honored() {
        let mut opening = game(&started(2).await);
        opening.bases.first = Some(opening.away.lineup[8].id.clone());
        let state = serde_json::to_value(&opening).unwrap();
        let (status, body) = post(
            "/step",
            json!({ "state": state, "call": "steal", "seed": 4 }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let events = body["result"]["baserunning"].as_array().unwrap();
        assert!(
            events
                .iter()
                .any(|event| event.get("StolenBase").is_some()
                    || event.get("CaughtStealing").is_some()),
            "no steal was tried: {events:?}"
        );
    }

    async fn runner_on_first() -> (Value, String) {
        let mut opening = game(&started(2).await);
        let runner = opening.away.lineup[8].id.clone();
        opening.bases.first = Some(runner.clone());
        (serde_json::to_value(&opening).unwrap(), runner)
    }

    fn baserunning(body: &Value) -> Vec<Value> {
        body["result"]["baserunning"].as_array().unwrap().clone()
    }

    #[tokio::test]
    async fn a_step_carries_the_ratings_of_the_runner_on_base() {
        let (state, runner) = runner_on_first().await;
        for (steal_success, event) in [(1.0, "StolenBase"), (0.0, "CaughtStealing")] {
            for seed in 0..20u64 {
                let (status, body) = post(
                    "/step",
                    json!({
                        "state": state,
                        "call": "steal",
                        "seed": seed,
                        "runners": { "first": { "id": runner, "steal_success": steal_success, "spd": 7.5 } },
                        "league_spd": 4.5,
                    }),
                )
                .await;
                assert_eq!(status, StatusCode::OK, "{body}");
                assert!(
                    baserunning(&body)
                        .iter()
                        .any(|e| e.get(event).is_some_and(|e| e["runner"] == runner.as_str())),
                    "steal_success {steal_success} with seed {seed}: {body}"
                );
            }
        }
    }

    #[tokio::test]
    async fn a_step_without_ratings_matches_one_with_empty_ratings() {
        let (state, _) = runner_on_first().await;
        let (_, bare) = post("/step", json!({ "state": state, "seed": 6 })).await;
        let (_, empty) = post(
            "/step",
            json!({ "state": state, "seed": 6, "runners": {}, "league_spd": null }),
        )
        .await;
        assert_eq!(bare, empty);
    }

    #[tokio::test]
    async fn a_rating_for_a_runner_who_is_not_on_that_base_is_rejected() {
        let (state, runner) = runner_on_first().await;
        let (status, body) = post(
            "/step",
            json!({ "state": state, "seed": 4, "runners": { "second": { "id": runner, "spd": 5.0 } } }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert!(body["error"]
            .as_str()
            .unwrap()
            .contains("invalid runner ratings"));

        let (status, body) = post(
            "/step",
            json!({ "state": state, "seed": 4, "runners": { "first": { "id": "someone-else" } } }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
    }

    #[tokio::test]
    async fn out_of_range_ratings_are_rejected() {
        let (state, runner) = runner_on_first().await;
        for running in [
            json!({ "runners": { "first": { "id": runner, "steal_success": 1.5 } } }),
            json!({ "runners": { "first": { "id": runner, "spd": -1.0 } } }),
            json!({ "league_spd": 0.0 }),
        ] {
            let mut request = json!({ "state": state, "seed": 4 });
            for (key, value) in running.as_object().unwrap() {
                request[key] = value.clone();
            }
            let (status, body) = post("/step", request).await;
            assert_eq!(
                status,
                StatusCode::UNPROCESSABLE_ENTITY,
                "{running}: {body}"
            );
        }
    }

    #[tokio::test]
    async fn a_hit_and_run_is_accepted() {
        let state = started(2).await;
        let (status, body) = post(
            "/step",
            json!({ "state": state, "call": "hit_and_run", "seed": 4 }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
    }

    #[tokio::test]
    async fn infield_in_holds_the_runner_on_third_on_a_ground_out() {
        let mut opening = game(&started(2).await);
        opening.bases.third = Some(opening.away.lineup[8].id.clone());
        let state = serde_json::to_value(&opening).unwrap();
        let mut ground_outs = 0;
        for seed in 0..200u64 {
            let (status, body) = post(
                "/step",
                json!({ "state": state, "call": "infield_in", "seed": seed }),
            )
            .await;
            assert_eq!(status, StatusCode::OK, "{body}");
            let outcome: PlateOutcome =
                serde_json::from_value(body["result"]["outcome"].clone()).unwrap();
            if outcome == PlateOutcome::GroundOut {
                ground_outs += 1;
                assert_eq!(body["result"]["change"]["runs_scored"], 0);
                assert_eq!(
                    body["state"]["bases"]["third"].as_str(),
                    opening.bases.third.as_deref()
                );
            }
        }
        assert!(ground_outs > 0, "no ground out in 200 seeds");
    }

    #[tokio::test]
    async fn a_fixture_without_batted_balls_plays_with_league_rates() {
        let opening = game(&started(2).await);
        let original: Value = serde_json::from_str(
            &std::fs::read_to_string(format!("{}/fixtures/game.json", env!("CARGO_MANIFEST_DIR")))
                .unwrap(),
        )
        .unwrap();
        assert!(original["away"]["lineup"][0].get("batted_balls").is_none());
        assert_eq!(
            opening.away.lineup[0].batted_balls,
            crate::model::BattedBallRates::default()
        );
        assert_eq!(
            opening.home.pitchers[0].batted_balls,
            crate::model::BattedBallRates::default()
        );
    }

    #[tokio::test]
    async fn a_none_call_plays_with_no_call_and_no_computer_call() {
        let state = started(2).await;
        let (status, body) = post(
            "/step",
            json!({ "state": state, "call": "none", "seed": 4 }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let outcome: PlateOutcome =
            serde_json::from_value(body["result"]["outcome"].clone()).unwrap();
        assert!(!matches!(
            outcome,
            PlateOutcome::BuntSingle
                | PlateOutcome::BuntSacrifice
                | PlateOutcome::BuntOut
                | PlateOutcome::IntentionalWalk
        ));
        let (_, again) = post(
            "/step",
            json!({ "state": state, "call": "none", "seed": 4 }),
        )
        .await;
        assert_eq!(again, body);
    }

    fn relief_card(id: &str) -> Value {
        json!({
            "id": id,
            "name": "Rex Relief",
            "defense": { "rating": 0, "measured_at": "P" },
            "rates": { "k": 0.3, "bb": 0.08, "hbp": 0.01, "hr": 0.02, "h": 0.17 },
            "fatigue": {
                "role": "reliever", "age": 29, "season_pitches_per_appearance": 18,
                "career_pitches_per_appearance": 18, "season_appearances": 60
            }
        })
    }

    #[tokio::test]
    async fn a_pitcher_brought_in_takes_the_mound_and_the_one_he_replaces_cannot_return() {
        let state = started(2).await;
        let starter = game(&state).home.pitcher_slot.clone().unwrap();
        let (status, body) = post(
            "/pitcher",
            json!({ "state": state, "pitcher": relief_card("h-rex"), "seed": 9 }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let changed = game(&body["state"]);
        assert_eq!(changed.home.pitcher_slot.as_deref(), Some("h-rex"));
        assert!(changed.home.unavailable.contains(&starter));
        assert!(changed.home.fatigue["h-rex"].ceiling > 0.0);
        assert!(changed
            .log
            .last()
            .unwrap()
            .text
            .contains("Rex Relief enters"));

        let (_, again) = post(
            "/pitcher",
            json!({ "state": state, "pitcher": relief_card("h-rex"), "seed": 9 }),
        )
        .await;
        assert_eq!(again, body, "the same seed drew a different fatigue line");

        let (status, stepped) = post("/step", json!({ "state": body["state"], "seed": 3 })).await;
        assert_eq!(status, StatusCode::OK, "{stepped}");
        assert_eq!(stepped["result"]["pitcher_id"], "h-rex");

        let starter_card = serde_json::to_value(
            changed
                .home
                .pitchers
                .iter()
                .find(|card| card.id == starter)
                .unwrap(),
        )
        .unwrap();
        let (status, refused) = post(
            "/pitcher",
            json!({ "state": stepped["state"], "pitcher": starter_card, "seed": 9 }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
        assert!(refused["error"]
            .as_str()
            .unwrap()
            .contains("cannot re-enter"));
    }

    #[tokio::test]
    async fn a_pitcher_card_with_bad_rates_or_a_batter_on_the_mound_is_rejected() {
        let state = started(2).await;
        let mut bad = relief_card("h-bad");
        bad["rates"]["k"] = json!(1.5);
        let (status, body) = post(
            "/pitcher",
            json!({ "state": state, "pitcher": bad, "seed": 1 }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");

        let batter = game(&state).home.lineup[0].id.clone();
        let (status, body) = post(
            "/pitcher",
            json!({ "state": state, "pitcher": relief_card(&batter), "seed": 1 }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
    }

    fn bench_card(id: &str, position: &str) -> Value {
        json!({
            "id": id,
            "name": "Benny Bench",
            "position": position,
            "defense": { "rating": 1, "measured_at": position },
            "wrc_plus": 90,
            "rates": {
                "k": 0.2, "bb": 0.08, "hbp": 0.01, "single": 0.15, "double": 0.04,
                "triple": 0.005, "hr": 0.02, "bip_out": 0.495
            }
        })
    }

    #[tokio::test]
    async fn a_substitute_takes_the_batting_order_slot_and_the_replaced_player_is_out() {
        let state = started(2).await;
        let opening = game(&state);
        let replaced = opening.away.lineup[0].clone();
        let position = serde_json::to_value(replaced.position).unwrap();
        let card = bench_card("a-bench", position.as_str().unwrap());
        let (status, body) = post(
            "/substitute",
            json!({ "state": state, "side": "away", "index": 0, "batter": card }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let changed = game(&body["state"]);
        assert_eq!(changed.away.lineup[0].id, "a-bench");
        assert!(changed.away.unavailable.contains(&replaced.id));
        assert!(changed.away.in_game.contains(&"a-bench".to_string()));
        assert!(!changed.away.in_game.contains(&replaced.id));
        assert!(changed
            .log
            .last()
            .unwrap()
            .text
            .contains("Benny Bench replaces"));

        let (status, stepped) = post("/step", json!({ "state": body["state"], "seed": 3 })).await;
        assert_eq!(status, StatusCode::OK, "{stepped}");
        assert_eq!(stepped["result"]["batter_id"], "a-bench");

        let mut back = serde_json::to_value(&replaced).unwrap();
        back["id"] = json!(replaced.id);
        let (status, refused) = post(
            "/substitute",
            json!({ "state": stepped["state"], "side": "away", "index": 0, "batter": back }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
        assert!(refused["error"]
            .as_str()
            .unwrap()
            .contains("cannot re-enter"));
    }

    #[tokio::test]
    async fn a_substitute_at_another_position_or_already_playing_is_rejected() {
        let state = started(2).await;
        let opening = game(&state);
        let other = if opening.away.lineup[0].position == crate::model::Position::Dh {
            "C"
        } else {
            "DH"
        };
        let (status, body) = post(
            "/substitute",
            json!({ "state": state, "side": "away", "index": 0, "batter": bench_card("a-x", other) }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");

        let mut playing = serde_json::to_value(&opening.away.lineup[1]).unwrap();
        playing["position"] = serde_json::to_value(opening.away.lineup[0].position).unwrap();
        let (status, body) = post(
            "/substitute",
            json!({ "state": state, "side": "away", "index": 0, "batter": playing }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");

        let (status, body) = post(
            "/substitute",
            json!({ "state": state, "side": "away", "index": 9, "batter": bench_card("a-y", "DH") }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
    }

    fn position_of(card: &crate::model::BatterCard) -> String {
        serde_json::to_value(card.position)
            .unwrap()
            .as_str()
            .unwrap()
            .to_string()
    }

    fn field_slot(opening: &Game, side: crate::model::Side) -> usize {
        opening
            .club(side)
            .lineup
            .iter()
            .position(|b| b.position != crate::model::Position::Dh)
            .unwrap()
    }

    fn dh_slot(opening: &Game, side: crate::model::Side) -> usize {
        opening
            .club(side)
            .lineup
            .iter()
            .position(|b| b.position == crate::model::Position::Dh)
            .unwrap()
    }

    /// The state with the batting order of `side` turned to `index` and the other club in the field.
    fn due_up(state: &Value, side: crate::model::Side, index: usize) -> Value {
        let mut opening = game(state);
        opening.club_mut(side).batter_index = index;
        opening.half = match side {
            crate::model::Side::Away => crate::model::Half::Top,
            crate::model::Side::Home => crate::model::Half::Bottom,
        };
        serde_json::to_value(&opening).unwrap()
    }

    /// The same state with the other club batting, as after the third out.
    fn turned_over(state: &Value) -> Value {
        let mut next = game(state);
        next.half = match next.half {
            crate::model::Half::Top => crate::model::Half::Bottom,
            crate::model::Half::Bottom => crate::model::Half::Top,
        };
        next.bases = crate::model::Bases::empty();
        serde_json::to_value(&next).unwrap()
    }

    async fn substitute_as(
        state: &Value,
        side: &str,
        index: usize,
        card: Value,
        role: &str,
    ) -> (StatusCode, Value) {
        post(
            "/substitute",
            json!({ "state": state, "side": side, "index": index, "batter": card, "role": role }),
        )
        .await
    }

    #[tokio::test]
    async fn a_pinch_hitter_bats_now_and_needs_a_position_before_his_club_pitches() {
        let state = started(2).await;
        let opening = game(&state);
        let slot = field_slot(&opening, crate::model::Side::Away);
        let state = due_up(&state, crate::model::Side::Away, slot);
        let position = position_of(&opening.away.lineup[slot]);
        let (status, body) = substitute_as(
            &state,
            "away",
            slot,
            bench_card("a-ph", &position),
            "pinch_hitter",
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let changed = game(&body["state"]);
        assert_eq!(changed.away.lineup[slot].id, "a-ph");
        assert_eq!(changed.away.pending, vec!["a-ph".to_string()]);
        assert!(changed.log.last().unwrap().text.contains("pinch hits for"));

        let (status, stepped) = post("/step", json!({ "state": body["state"], "seed": 3 })).await;
        assert_eq!(status, StatusCode::OK, "{stepped}");
        assert_eq!(stepped["result"]["batter_id"], "a-ph");

        let fielding = turned_over(&body["state"]);
        let (status, refused) = post("/step", json!({ "state": fielding, "seed": 3 })).await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
        assert!(refused["error"]
            .as_str()
            .unwrap()
            .contains("a-ph needs a fielding position"));
        let (status, _) = post("/matchup", json!({ "state": fielding })).await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);

        let (status, placed) = post(
            "/positions",
            json!({ "state": fielding, "side": "away", "changes": [
                { "index": slot, "position": position, "defense": { "rating": 2.5, "measured_at": position } }
            ] }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{placed}");
        let placed_game = game(&placed["state"]);
        assert!(placed_game.away.pending.is_empty());
        assert_eq!(
            placed_game.defense_rating(crate::model::Side::Away),
            game(&fielding).defense_rating(crate::model::Side::Away) - 1.0 + 2.5,
            "team defense was not recomputed from the card at his slot"
        );
        let (status, stepped) = post("/step", json!({ "state": placed["state"], "seed": 3 })).await;
        assert_eq!(status, StatusCode::OK, "{stepped}");
    }

    #[tokio::test]
    async fn a_pinch_hitter_must_replace_the_batter_due_up() {
        let state = started(2).await;
        let opening = game(&state);
        let position = position_of(&opening.away.lineup[3]);
        let (status, body) = substitute_as(
            &state,
            "away",
            3,
            bench_card("a-ph", &position),
            "pinch_hitter",
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        assert!(body["error"].as_str().unwrap().contains("batter due up"));

        let position = position_of(&opening.home.lineup[0]);
        let (status, body) = substitute_as(
            &state,
            "home",
            0,
            bench_card("h-ph", &position),
            "pinch_hitter",
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
    }

    #[tokio::test]
    async fn a_pinch_hitter_for_the_designated_hitter_is_the_designated_hitter() {
        let state = started(2).await;
        let opening = game(&state);
        let slot = dh_slot(&opening, crate::model::Side::Away);
        let state = due_up(&state, crate::model::Side::Away, slot);
        let (status, body) = substitute_as(
            &state,
            "away",
            slot,
            bench_card("a-dh", "DH"),
            "pinch_hitter",
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let changed = game(&body["state"]);
        assert!(changed.away.pending.is_empty());
        assert_eq!(
            changed.away.lineup[slot].position,
            crate::model::Position::Dh
        );

        let fielding = turned_over(&body["state"]);
        let (status, stepped) = post("/step", json!({ "state": fielding, "seed": 3 })).await;
        assert_eq!(status, StatusCode::OK, "{stepped}");

        let catcher = changed
            .away
            .lineup
            .iter()
            .position(|b| b.position == crate::model::Position::Catcher)
            .unwrap();
        let (status, refused) = post(
            "/positions",
            json!({ "state": fielding, "side": "away", "changes": [
                { "index": slot, "position": "C", "defense": { "rating": 0, "measured_at": "C" } },
                { "index": catcher, "position": "DH", "defense": { "rating": 0, "measured_at": "DH" } }
            ] }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
        assert!(refused["error"]
            .as_str()
            .unwrap()
            .contains("designated hitter"));
    }

    #[tokio::test]
    async fn a_pinch_runner_takes_the_base_and_the_slot() {
        let (state, runner) = runner_on_first().await;
        let opening = game(&state);
        let slot = opening
            .away
            .lineup
            .iter()
            .position(|b| b.id == runner)
            .unwrap();
        let position = position_of(&opening.away.lineup[slot]);
        let (status, body) = substitute_as(
            &state,
            "away",
            slot,
            bench_card("a-pr", &position),
            "pinch_runner",
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let changed = game(&body["state"]);
        assert_eq!(changed.bases.first.as_deref(), Some("a-pr"));
        assert_eq!(changed.away.lineup[slot].id, "a-pr");
        assert!(changed.away.unavailable.contains(&runner));
        if changed.away.lineup[slot].position != crate::model::Position::Dh {
            assert_eq!(changed.away.pending, vec!["a-pr".to_string()]);
        }
        assert!(changed.log.last().unwrap().text.contains("pinch runs for"));

        let (status, refused) = substitute_as(
            &body["state"],
            "away",
            0,
            bench_card("a-pr2", &position_of(&opening.away.lineup[0])),
            "pinch_runner",
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
        assert!(refused["error"].as_str().unwrap().contains("not on base"));
    }

    #[tokio::test]
    async fn a_defensive_replacement_enters_only_in_the_field_and_changes_the_defense() {
        let state = started(2).await;
        let opening = game(&state);
        let slot = field_slot(&opening, crate::model::Side::Home);
        let position = position_of(&opening.home.lineup[slot]);
        let mut glove = bench_card("h-glove", &position);
        glove["defense"]["rating"] = json!(9.0);
        let (status, body) = substitute_as(&state, "home", slot, glove.clone(), "defense").await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let changed = game(&body["state"]);
        assert!(changed.home.pending.is_empty());
        assert_eq!(
            changed.defense_rating(crate::model::Side::Home),
            opening.defense_rating(crate::model::Side::Home)
                - opening.home.lineup[slot].defense.rating
                + 9.0
        );

        let slot = field_slot(&opening, crate::model::Side::Away);
        let position = position_of(&opening.away.lineup[slot]);
        let (status, refused) = substitute_as(
            &state,
            "away",
            slot,
            bench_card("a-glove", &position),
            "defense",
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
        assert!(refused["error"].as_str().unwrap().contains("in the field"));
    }

    #[tokio::test]
    async fn fielders_can_switch_positions_but_every_position_is_covered_once() {
        let state = started(2).await;
        let opening = game(&state);
        let fielders: Vec<usize> = (0..9)
            .filter(|i| opening.home.lineup[*i].position != crate::model::Position::Dh)
            .take(2)
            .collect();
        let (a, b) = (fielders[0], fielders[1]);
        let (pa, pb) = (
            position_of(&opening.home.lineup[a]),
            position_of(&opening.home.lineup[b]),
        );
        let (status, body) = post(
            "/positions",
            json!({ "state": state, "side": "home", "changes": [
                { "index": a, "position": pb, "defense": { "rating": 0.5, "measured_at": pb } },
                { "index": b, "position": pa, "defense": { "rating": 0.25, "measured_at": pa } }
            ] }),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let changed = game(&body["state"]);
        assert_eq!(position_of(&changed.home.lineup[a]), pb);
        assert_eq!(position_of(&changed.home.lineup[b]), pa);

        let (status, refused) = post(
            "/positions",
            json!({ "state": state, "side": "home", "changes": [
                { "index": a, "position": pb, "defense": { "rating": 0.5, "measured_at": pb } }
            ] }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
        assert!(refused["error"]
            .as_str()
            .unwrap()
            .contains("exactly one fielder"));

        let (status, refused) = post(
            "/positions",
            json!({ "state": state, "side": "away", "changes": [
                { "index": a, "position": pa, "defense": { "rating": 0.5, "measured_at": pa } }
            ] }),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{refused}");
    }

    #[tokio::test]
    async fn a_saved_state_without_pending_players_still_plays() {
        let mut state = started(2).await;
        state["away"].as_object_mut().unwrap().remove("pending");
        state["home"].as_object_mut().unwrap().remove("pending");
        let (status, body) = post("/step", json!({ "state": state, "seed": 3 })).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let (status, body) = post(
            "/substitute",
            json!({ "state": started(2).await, "side": "away", "index": 0,
                    "batter": bench_card("a-bench", &position_of(&game(&started(2).await).away.lineup[0])) }),
        )
        .await;
        assert_eq!(
            status,
            StatusCode::OK,
            "an omitted role is a plain replacement: {body}"
        );
    }

    #[tokio::test]
    async fn an_unknown_call_is_rejected() {
        let state = started(2).await;
        let (status, body) = post(
            "/step",
            json!({ "state": state, "call": "squeeze", "seed": 4 }),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(body["error"].as_str().unwrap().contains("intentional_walk"));
    }

    #[tokio::test]
    async fn a_malformed_state_is_rejected() {
        let (status, body) = post("/step", json!({ "state": { "inning": 1 }, "seed": 4 })).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(body["error"].is_string());
    }

    #[tokio::test]
    async fn matchup_reports_the_draw_without_drawing() {
        let state = started(8).await;
        let (status, body) = post("/matchup", json!({ "state": state })).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let opening = game(&state);
        assert_eq!(body["batter_id"], opening.away.lineup[0].id);
        assert_eq!(
            body["pitcher_id"].as_str(),
            opening.home.pitcher_slot.as_deref()
        );
        assert_eq!(body["pitcher_entering"], false);
        let probabilities = body["probabilities"].as_object().unwrap();
        for key in [
            "k", "bb", "hbp", "single", "double", "triple", "hr", "bip_out",
        ] {
            assert!(probabilities[key].is_f64(), "{key} is missing");
        }
        let sum: f64 = probabilities
            .values()
            .map(|value| value.as_f64().unwrap())
            .sum();
        assert!((sum - 1.0).abs() < 1e-9, "probabilities sum to {sum}");

        let (_, again) = post("/matchup", json!({ "state": state })).await;
        assert_eq!(again, body, "matchup is not a pure read");
    }

    #[tokio::test]
    async fn matchup_names_the_pitcher_who_will_enter_on_an_empty_mound() {
        let mut opening = game(&started(8).await);
        let starter = opening.home.pitcher_slot.take().unwrap();
        opening.home.in_game.retain(|id| id != &starter);
        opening.home.unavailable.push(starter);
        let entering = opening.home.available[0].clone();
        let state = serde_json::to_value(&opening).unwrap();
        let (status, body) = post("/matchup", json!({ "state": state })).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        assert_eq!(body["pitcher_id"], entering);
        assert_eq!(body["pitcher_entering"], true);
    }
}
