//! Layer B. A distribution against true talent, not one box score.
//!
//! Seed `20261004` repeats this check. It is not a box-score seed and `play` does not read it.
//! Each plate appearance is its own draw. Replaying one input is not how a game is rebuilt.
//!
//! Sample: 40_000 plate appearances.
//! Band: batting average within 0.012 of .300.

use baseball_engine::runner::step_plate_appearance;
use baseball_engine::{
    batted_ball_mix, card_batting_average, load_json, outcome_probabilities, Bases,
    BattedBallRates, BatterCard, ComputerManager, DefenseRating, DistributionFixture,
    FatigueProfile, Game, GameFixture, Governance, Half, HitterRates, PaInput, PaResult, Park,
    PitcherCard, PitcherRates, PitcherRole, PlateOutcome, Position, PrePaCalls, Running, Sim,
    Situation, TeamFixture, COMPUTER_BUNT_RATE, DP_RATE, FLY_SECOND_TO_THIRD, GB_SCORE_FROM_THIRD,
    GB_SECOND_TO_THIRD, INFIELD_IN_SINGLE_SHIFT, LEAGUE_BB, LEAGUE_FB, LEAGUE_GB, LEAGUE_H,
    LEAGUE_HBP, LEAGUE_HR, LEAGUE_K, LEAGUE_LD, SF_RATE,
};

const DISTRIBUTION_SEED: u64 = 20_261_004;
const DISTRIBUTION_SAMPLE: usize = 40_000;
const DISTRIBUTION_BAND: f64 = 0.012;

fn fixture() -> DistributionFixture {
    let path = format!("{}/fixtures/distribution.json", env!("CARGO_MANIFEST_DIR"));
    load_json(&path).unwrap()
}

fn input_from(fixture: &DistributionFixture, wrc_plus: f64, weather: Option<String>) -> PaInput {
    PaInput {
        hitter_id: fixture.id.clone(),
        hitter_name: fixture.id.clone(),
        rates: fixture.rates.clone(),
        wrc_plus,
        pitcher_id: "league".into(),
        pitcher_name: "League".into(),
        pitcher: fixture.pitcher.clone(),
        hitter_batted_balls: BattedBallRates::default(),
        pitcher_batted_balls: BattedBallRates::default(),
        defense: fixture.defense.rating,
        situation: Situation {
            inning: 1,
            half: Half::Top,
            outs: 0,
            bases: Bases::empty(),
            away_score: 0,
            home_score: 0,
            pitcher_fatigue: 0.0,
            pitcher_ceiling: 100.0,
            postseason: false,
        },
        park: fixture.park.clone(),
        weather,
        calls: PrePaCalls::default(),
        running: Running::default(),
    }
}

#[test]
fn stub_hitter_rated_300_lands_near_300() {
    let fixture = fixture();
    assert!((fixture.rates.sum() - 1.0).abs() < 1e-6);
    assert!((fixture.pitcher.k - LEAGUE_K).abs() < 1e-12);
    assert!((fixture.pitcher.bb - LEAGUE_BB).abs() < 1e-12);
    assert!((fixture.pitcher.hbp - LEAGUE_HBP).abs() < 1e-12);
    assert!((fixture.pitcher.hr - LEAGUE_HR).abs() < 1e-12);
    assert!((fixture.pitcher.h - LEAGUE_H).abs() < 1e-12);
    assert!((fixture.defense.rating - 0.0).abs() < 1e-12);
    assert!((fixture.park.run_factor - 1.0).abs() < 1e-12);

    let analytic = outcome_probabilities(&fixture.rates, &fixture.pitcher, 0.0, 1.0);
    let card = card_batting_average(&fixture.rates);
    assert!((card - 0.300).abs() < 1e-9, "card batting average {card}");
    assert!(
        (analytic.batting_average() - 0.300).abs() < 1e-9,
        "matched batting average {}",
        analytic.batting_average()
    );

    let input = input_from(&fixture, fixture.wrc_plus, fixture.weather.clone());
    let mut sim = Sim::from_seed(DISTRIBUTION_SEED);
    let mut hits = 0.0;
    let mut at_bats = 0.0;
    for _ in 0..DISTRIBUTION_SAMPLE {
        let result = sim.resolve(&input);
        match result.outcome {
            PlateOutcome::Walk | PlateOutcome::HitByPitch | PlateOutcome::IntentionalWalk => {}
            PlateOutcome::Single
            | PlateOutcome::Double
            | PlateOutcome::Triple
            | PlateOutcome::HomeRun => {
                hits += 1.0;
                at_bats += 1.0;
            }
            PlateOutcome::CaughtStealing => {}
            _ => at_bats += 1.0,
        }
    }
    let average = hits / at_bats;
    let gap = (average - 0.300_f64).abs();
    assert!(
        gap <= DISTRIBUTION_BAND,
        "batting average {average} from {hits} hits and {at_bats} at-bats over {DISTRIBUTION_SAMPLE} plate appearances (seed {DISTRIBUTION_SEED})"
    );
}

#[test]
fn the_same_seed_repeats_the_check_and_is_not_a_game() {
    let fixture = fixture();
    let input = input_from(&fixture, 100.0, None);
    let mut first = Sim::from_seed(DISTRIBUTION_SEED);
    let mut second = Sim::from_seed(DISTRIBUTION_SEED);
    let left = first.resolve(&input);
    let right = second.resolve(&input);
    assert_eq!(left.outcome, right.outcome);
    assert_eq!(left.pitches, right.pitches);
}

#[test]
fn wrc_plus_and_weather_do_not_change_the_draw() {
    let fixture = fixture();
    let weak = input_from(&fixture, 60.0, None);
    let strong = input_from(&fixture, 160.0, Some("wind".into()));
    let mut left = Sim::from_seed(DISTRIBUTION_SEED);
    let mut right = Sim::from_seed(DISTRIBUTION_SEED);
    let a = left.resolve(&weak);
    let b = right.resolve(&strong);
    assert_eq!(a.outcome, b.outcome);
    assert_eq!(a.pitches, b.pitches);
    assert_eq!(a.change, b.change);
}

/// Manager bunt check. Seed `20261005`. Sample 100_000 calls.
/// Band: bunt rate from 0.006 to 0.010. Intentional walks, steals, and hit-and-runs are 0.
#[test]
fn computer_bunt_rate_is_about_0_8_percent_and_intentional_walks_are_zero() {
    let mut manager = ComputerManager::from_seed(20_261_005);
    let sample = 100_000;
    let mut bunts = 0;
    let mut walks = 0;
    let mut steals = 0;
    let mut hit_and_runs = 0;
    for _ in 0..sample {
        let calls = manager.pre_pa_calls();
        bunts += i32::from(calls.bunt);
        walks += i32::from(calls.intentional_walk);
        steals += i32::from(calls.steal);
        hit_and_runs += i32::from(calls.hit_and_run);
    }
    let rate = f64::from(bunts) / f64::from(sample);
    assert_eq!(COMPUTER_BUNT_RATE, 0.008);
    assert!(
        (0.006..0.010).contains(&rate),
        "bunt rate {rate} over {sample} calls"
    );
    assert_eq!(walks, 0);
    assert_eq!(steals, 0);
    assert_eq!(hit_and_runs, 0);
}

#[test]
fn neutral_park_constant_is_one() {
    let park = Park {
        id: "neutral".into(),
        run_factor: 1.0,
    };
    assert!((park.run_factor - 1.0).abs() < 1e-12);
}

fn league_hitter() -> HitterRates {
    let single = 0.1425;
    let double = 0.0453;
    let triple = LEAGUE_H - single - double;
    HitterRates {
        k: LEAGUE_K,
        bb: LEAGUE_BB,
        hbp: LEAGUE_HBP,
        single,
        double,
        triple,
        hr: LEAGUE_HR,
        bip_out: 1.0 - (LEAGUE_K + LEAGUE_BB + LEAGUE_HBP + LEAGUE_H + LEAGUE_HR),
    }
}

fn league_pitcher() -> PitcherRates {
    PitcherRates {
        k: LEAGUE_K,
        bb: LEAGUE_BB,
        hbp: LEAGUE_HBP,
        hr: LEAGUE_HR,
        h: LEAGUE_H,
    }
}

/// A league-average hitter against a league-average pitcher, neutral park and defense.
fn league_input(bases: Bases, outs: u8, calls: PrePaCalls) -> PaInput {
    PaInput {
        hitter_id: "batter".into(),
        hitter_name: "Batter".into(),
        rates: league_hitter(),
        wrc_plus: 100.0,
        pitcher_id: "league".into(),
        pitcher_name: "League".into(),
        pitcher: league_pitcher(),
        hitter_batted_balls: BattedBallRates::default(),
        pitcher_batted_balls: BattedBallRates::default(),
        defense: 0.0,
        situation: Situation {
            inning: 1,
            half: Half::Top,
            outs,
            bases,
            away_score: 0,
            home_score: 0,
            pitcher_fatigue: 0.0,
            pitcher_ceiling: 100.0,
            postseason: false,
        },
        park: Park {
            id: "neutral".into(),
            run_factor: 1.0,
        },
        weather: None,
        calls,
        running: Running::default(),
    }
}

fn runners(first: bool, second: bool, third: bool) -> Bases {
    Bases {
        first: first.then(|| "r1".to_string()),
        second: second.then(|| "r2".to_string()),
        third: third.then(|| "r3".to_string()),
    }
}

fn resolve_many(input: &PaInput, seed: u64, sample: usize) -> Vec<PaResult> {
    let mut sim = Sim::from_seed(seed);
    (0..sample).map(|_| sim.resolve(input)).collect()
}

fn count(results: &[PaResult], outcome: PlateOutcome) -> usize {
    results.iter().filter(|r| r.outcome == outcome).count()
}

fn share(part: usize, whole: usize) -> f64 {
    part as f64 / whole.max(1) as f64
}

/// Batted-ball checks. Seed `20261068`. Sample 60_000 plate appearances per situation.
/// Band: each rolled rate within 0.03 of its constant.
const BATTED_BALL_SEED: u64 = 20_261_068;
const BATTED_BALL_SAMPLE: usize = 60_000;
const BATTED_BALL_BAND: f64 = 0.03;

fn assert_near(measured: f64, expected: f64, what: &str) {
    assert!(
        (measured - expected).abs() <= BATTED_BALL_BAND,
        "{what}: measured {measured}, expected {expected} (seed {BATTED_BALL_SEED})"
    );
}

#[test]
fn ball_in_play_outs_split_by_the_league_batted_ball_mix() {
    let results = resolve_many(
        &league_input(Bases::empty(), 0, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE,
    );
    let ground = count(&results, PlateOutcome::GroundOut);
    let fly = count(&results, PlateOutcome::FlyOut);
    let line = count(&results, PlateOutcome::LineOut);
    let outs = ground + fly + line;
    assert_eq!(count(&results, PlateOutcome::BipOut), 0);
    assert_near(share(ground, outs), LEAGUE_GB, "ground-out share");
    assert_near(share(fly, outs), LEAGUE_FB, "fly-out share");
    assert_near(share(line, outs), LEAGUE_LD, "line-out share");
}

#[test]
fn a_ground_ball_pitcher_gets_more_ground_outs() {
    let mut input = league_input(Bases::empty(), 0, PrePaCalls::default());
    let league = resolve_many(&input, BATTED_BALL_SEED, BATTED_BALL_SAMPLE);
    input.pitcher_batted_balls = BattedBallRates {
        gb: 0.55,
        fb: 0.28,
        ld: 0.17,
    };
    let sinker = resolve_many(&input, BATTED_BALL_SEED, BATTED_BALL_SAMPLE);
    let expected = batted_ball_mix(&input.hitter_batted_balls, &input.pitcher_batted_balls);
    let ground = count(&sinker, PlateOutcome::GroundOut);
    let outs =
        ground + count(&sinker, PlateOutcome::FlyOut) + count(&sinker, PlateOutcome::LineOut);
    assert!(expected.gb > LEAGUE_GB);
    assert_near(
        share(ground, outs),
        expected.gb,
        "ground-out share against a sinkerballer",
    );
    assert!(ground > count(&league, PlateOutcome::GroundOut));
}

#[test]
fn ground_outs_with_a_runner_on_first_turn_two_at_the_double_play_rate() {
    let results = resolve_many(
        &league_input(runners(true, false, false), 0, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE,
    );
    let double_plays = count(&results, PlateOutcome::GroundedIntoDoublePlay);
    let ground_outs = count(&results, PlateOutcome::GroundOut);
    assert_near(
        share(double_plays, double_plays + ground_outs),
        DP_RATE,
        "double plays per ground ball out",
    );
    for result in results
        .iter()
        .filter(|r| r.outcome == PlateOutcome::GroundedIntoDoublePlay)
    {
        assert_eq!(result.change.outs_added, 2);
        assert_eq!(result.change.bases, Bases::empty());
        assert!(result.outcome.is_at_bat());
    }
    for result in results
        .iter()
        .filter(|r| r.outcome == PlateOutcome::GroundOut)
    {
        let forced = Bases {
            second: Some("r1".into()),
            ..Bases::empty()
        };
        assert_eq!(result.change.bases, forced);
    }
}

#[test]
fn ground_outs_score_the_unforced_runner_from_third_at_the_stated_rate() {
    let results = resolve_many(
        &league_input(runners(false, false, true), 1, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE,
    );
    let ground: Vec<_> = results
        .iter()
        .filter(|r| r.outcome == PlateOutcome::GroundOut)
        .collect();
    let scored = ground.iter().filter(|r| r.change.runs_scored == 1).count();
    assert_near(
        share(scored, ground.len()),
        GB_SCORE_FROM_THIRD,
        "scored from third on a ground out",
    );
}

#[test]
fn ground_outs_move_the_unforced_runner_from_second_at_the_stated_rate() {
    let results = resolve_many(
        &league_input(runners(false, true, false), 0, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE,
    );
    let ground: Vec<_> = results
        .iter()
        .filter(|r| r.outcome == PlateOutcome::GroundOut)
        .collect();
    let moved = ground
        .iter()
        .filter(|r| r.change.bases.third.is_some())
        .count();
    assert_near(
        share(moved, ground.len()),
        GB_SECOND_TO_THIRD,
        "second to third on a ground out",
    );
}

#[test]
fn fly_outs_score_the_runner_from_third_at_the_sacrifice_fly_rate() {
    let results = resolve_many(
        &league_input(runners(false, true, true), 0, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE,
    );
    let sacrifices: Vec<_> = results
        .iter()
        .filter(|r| r.outcome == PlateOutcome::SacrificeFly)
        .collect();
    let held = count(&results, PlateOutcome::FlyOut);
    assert_near(
        share(sacrifices.len(), sacrifices.len() + held),
        SF_RATE,
        "sacrifice flies per fly out",
    );
    let tagged = sacrifices
        .iter()
        .filter(|r| r.change.bases.third.is_some())
        .count();
    assert_near(
        share(tagged, sacrifices.len()),
        FLY_SECOND_TO_THIRD,
        "second to third on a fly out",
    );
    for result in sacrifices {
        assert_eq!(result.change.runs_scored, 1);
        assert_eq!(result.change.outs_added, 1);
        assert!(!result.outcome.is_at_bat());
    }
}

#[test]
fn line_outs_move_nobody() {
    let bases = runners(true, true, true);
    let results = resolve_many(
        &league_input(bases.clone(), 0, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE / 4,
    );
    let lines: Vec<_> = results
        .iter()
        .filter(|r| r.outcome == PlateOutcome::LineOut)
        .collect();
    assert!(!lines.is_empty());
    for result in lines {
        assert_eq!(result.change.outs_added, 1);
        assert_eq!(result.change.runs_scored, 0);
        assert_eq!(result.change.bases, bases);
    }
}

#[test]
fn with_two_outs_an_out_ends_the_inning_and_nobody_advances() {
    let bases = runners(true, true, true);
    let results = resolve_many(
        &league_input(bases.clone(), 2, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE / 4,
    );
    assert_eq!(count(&results, PlateOutcome::GroundedIntoDoublePlay), 0);
    assert_eq!(count(&results, PlateOutcome::SacrificeFly), 0);
    let outs: Vec<_> = results
        .iter()
        .filter(|r| {
            matches!(
                r.outcome,
                PlateOutcome::GroundOut | PlateOutcome::FlyOut | PlateOutcome::LineOut
            )
        })
        .collect();
    assert!(!outs.is_empty());
    for result in outs {
        assert_eq!(result.change.outs_added, 1);
        assert_eq!(result.change.runs_scored, 0);
        assert_eq!(result.change.bases, bases);
    }
}

#[test]
fn infield_in_holds_the_runner_and_turns_a_tenth_of_ground_outs_into_singles() {
    let calls = PrePaCalls {
        infield_in: true,
        ..PrePaCalls::default()
    };
    let normal = resolve_many(
        &league_input(runners(false, false, true), 0, PrePaCalls::default()),
        BATTED_BALL_SEED,
        BATTED_BALL_SAMPLE,
    );
    let drawn_in = resolve_many(
        &league_input(runners(false, false, true), 0, calls),
        BATTED_BALL_SEED + 1,
        BATTED_BALL_SAMPLE,
    );
    for result in drawn_in
        .iter()
        .filter(|r| r.outcome == PlateOutcome::GroundOut)
    {
        assert_eq!(result.change.runs_scored, 0);
        assert_eq!(result.change.bases.third.as_deref(), Some("r3"));
    }
    let kept = share(
        count(&drawn_in, PlateOutcome::GroundOut),
        count(&normal, PlateOutcome::GroundOut),
    );
    assert_near(
        kept,
        1.0 - INFIELD_IN_SINGLE_SHIFT,
        "ground outs kept with the infield in",
    );
    assert!(count(&drawn_in, PlateOutcome::Single) > count(&normal, PlateOutcome::Single));
}

#[test]
fn infield_in_is_ignored_without_a_runner_on_third_or_with_two_outs() {
    let calls = PrePaCalls {
        infield_in: true,
        ..PrePaCalls::default()
    };
    for (bases, outs) in [
        (runners(true, true, false), 0u8),
        (runners(false, false, true), 2u8),
    ] {
        let normal = resolve_many(
            &league_input(bases.clone(), outs, PrePaCalls::default()),
            BATTED_BALL_SEED,
            2_000,
        );
        let called = resolve_many(&league_input(bases, outs, calls), BATTED_BALL_SEED, 2_000);
        assert_eq!(normal, called);
    }
}

/// Layer C. Whole games. Seed `20261069`. 2_000 games of league-average lineups against
/// league-average pitching in a neutral park, under the computer manager.
/// Bands: 4.2 to 4.9 runs per team per game; double plays on 9% to 13% of opportunities,
/// an opportunity being a plate appearance with a runner on first and fewer than two outs.
const CALIBRATION_SEED: u64 = 20_261_069;
const CALIBRATION_GAMES: u64 = 2_000;

const LINEUP_POSITIONS: [Position; 9] = [
    Position::Center,
    Position::Shortstop,
    Position::Dh,
    Position::First,
    Position::Right,
    Position::Left,
    Position::Third,
    Position::Catcher,
    Position::Second,
];

fn league_pitcher_card(id: String, role: PitcherRole, pitches: f64) -> PitcherCard {
    PitcherCard {
        id: id.clone(),
        name: id,
        defense: DefenseRating {
            rating: 0.0,
            measured_at: Position::Pitcher,
        },
        rates: league_pitcher(),
        fatigue: FatigueProfile {
            role,
            age: 28,
            season_pitches_per_appearance: pitches,
            career_pitches_per_appearance: pitches,
            season_appearances: 30,
        },
        batted_balls: BattedBallRates::default(),
    }
}

fn league_team(id: &str) -> TeamFixture {
    let lineup = LINEUP_POSITIONS
        .iter()
        .enumerate()
        .map(|(index, position)| BatterCard {
            id: format!("{id}-b{index}"),
            name: format!("{id} {index}"),
            position: *position,
            defense: DefenseRating {
                rating: 0.0,
                measured_at: *position,
            },
            wrc_plus: 100.0,
            rates: league_hitter(),
            batted_balls: BattedBallRates::default(),
        })
        .collect();
    let mut pitchers = vec![league_pitcher_card(
        format!("{id}-sp"),
        PitcherRole::Starter,
        95.0,
    )];
    for index in 0..10 {
        pitchers.push(league_pitcher_card(
            format!("{id}-rp{index}"),
            PitcherRole::Reliever,
            25.0,
        ));
    }
    TeamFixture {
        id: id.into(),
        name: id.into(),
        home_park_id: "neutral".into(),
        lineup,
        pitchers,
    }
}

fn league_fixture() -> GameFixture {
    GameFixture {
        postseason: false,
        parks: vec![Park {
            id: "neutral".into(),
            run_factor: 1.0,
        }],
        weather: None,
        away: league_team("away"),
        home: league_team("home"),
    }
}

#[test]
fn league_average_games_land_in_the_run_and_double_play_bands() {
    let mut runs = 0u64;
    let mut opportunities = 0u64;
    let mut double_plays = 0u64;
    let mut manager = ComputerManager::from_seed(CALIBRATION_SEED);
    let mut sim = Sim::from_seed(CALIBRATION_SEED);
    let governance = Governance::new();
    for game_index in 0..CALIBRATION_GAMES {
        let mut game = Game::start(league_fixture(), CALIBRATION_SEED + game_index).unwrap();
        let mut guard = 0;
        while !game.is_final() {
            guard += 1;
            assert!(guard < 2_000, "game {game_index} did not end");
            let opportunity = game.bases.first.is_some() && game.outs < 2;
            step_plate_appearance(
                &mut game,
                &mut sim,
                &mut manager,
                &governance,
                None,
                &Running::default(),
            )
            .unwrap();
            if opportunity {
                opportunities += 1;
                let result = game.last_result.as_ref().unwrap();
                if result.outcome == PlateOutcome::GroundedIntoDoublePlay {
                    double_plays += 1;
                }
            }
        }
        runs += u64::from(game.score.away + game.score.home);
    }
    let per_team = runs as f64 / (2 * CALIBRATION_GAMES) as f64;
    let dp_rate = double_plays as f64 / opportunities as f64;
    assert!(
        (4.2..=4.9).contains(&per_team),
        "{per_team} runs per team per game over {CALIBRATION_GAMES} games (seed {CALIBRATION_SEED})"
    );
    assert!(
        (0.09..=0.13).contains(&dp_rate),
        "double plays on {dp_rate} of {opportunities} opportunities (seed {CALIBRATION_SEED})"
    );
}
