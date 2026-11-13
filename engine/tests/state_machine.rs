//! Layer A. Exact state-machine cases. These do not need the simulator.

use baseball_engine::{
    load_json, play_game, Bases, BattedBallRates, ComputerManager, Game, GameError, GameFixture,
    Governance, Half, PlateOutcome, Position, Side, Sim, Status,
};

fn game(postseason: bool) -> Game {
    Game::start(baseball_engine::harness::scripted_fixture(postseason), 1).unwrap()
}

#[test]
fn four_outs_are_rejected_and_do_not_change_state() {
    let mut game = game(false);
    game.outs = 2;
    let mut result = baseball_engine::harness::holding_out(&game.bases);
    result.change.outs_added = 2;
    let outs = game.outs;
    let log = game.log.len();
    let score = game.score.clone();
    let err = game.apply_plate_appearance(result).unwrap_err();
    assert_eq!(err, GameError::FourOuts { outs: 2, added: 2 });
    assert_eq!(game.outs, outs);
    assert_eq!(game.log.len(), log);
    assert_eq!(game.score, score);
    assert!(game.last_result.is_none());
}

#[test]
fn the_third_out_is_legal_and_ends_the_half() {
    let mut game = game(false);
    game.outs = 2;
    game.apply_plate_appearance(baseball_engine::harness::holding_out(&game.bases))
        .unwrap();
    assert_eq!(game.outs, 0);
    assert_eq!(game.half, Half::Bottom);
    assert_eq!(game.inning, 1);
    assert_eq!(game.status, Status::InProgress);
}

#[test]
fn a_used_pitcher_cannot_reenter() {
    let mut game = game(false);
    let starter = game.home.pitcher_slot.clone().unwrap();
    let next = game.home.available[0].clone();
    let mut manager = ComputerManager::from_seed(1);
    manager.choose(&mut game, &next).unwrap();
    assert!(game.home.unavailable.contains(&starter));
    assert!(!game.home.in_game.contains(&starter));
    let err = manager.choose(&mut game, &starter).unwrap_err();
    assert_eq!(err, GameError::Reentry { player: starter });
    assert_eq!(game.home.pitcher_slot.as_deref(), Some(next.as_str()));
}

#[test]
fn fatigue_pulls_between_plate_appearances_and_blocks_the_spent_pitcher() {
    let mut game = game(false);
    let starter = game.home.pitcher_slot.clone().unwrap();
    {
        let state = game.home.fatigue.get_mut(&starter).unwrap();
        state.effort = 0.0;
        state.ceiling = 3.0;
    }
    let log_before = game.log.len();
    game.apply_plate_appearance(baseball_engine::harness::pitches_only(4))
        .unwrap();
    assert!(game.log.len() > log_before);
    assert!(game.last_result.is_some(), "the plate appearance finished");
    assert!(
        game.home.pitcher_slot.is_none(),
        "the mound is empty after the pull"
    );
    assert!(game.home.unavailable.contains(&starter));
    let pull_at = game
        .log
        .iter()
        .position(|entry| entry.text.contains("is pulled"))
        .expect("pull is logged");
    let pa_at = game
        .log
        .iter()
        .position(|entry| entry.text.contains("walked"))
        .expect("the plate appearance is logged");
    assert!(pa_at < pull_at, "the plate appearance is not interrupted");

    let err = game
        .apply_plate_appearance(baseball_engine::harness::pitches_only(1))
        .unwrap_err();
    assert_eq!(err, GameError::PitcherRequired);

    let mut manager = ComputerManager::from_seed(2);
    let err = manager.choose(&mut game, &starter).unwrap_err();
    assert_eq!(
        err,
        GameError::Reentry {
            player: starter.clone()
        }
    );

    manager.assign_next(&mut game).unwrap();
    assert!(game.home.pitcher_slot.is_some());
    assert_ne!(game.home.pitcher_slot.as_deref(), Some(starter.as_str()));
    game.apply_plate_appearance(baseball_engine::harness::holding_out(&game.bases))
        .unwrap();
}

#[test]
fn a_pitcher_left_in_past_the_fatigue_line_is_rejected() {
    let mut game = game(false);
    let starter = game.home.pitcher_slot.clone().unwrap();
    {
        let state = game.home.fatigue.get_mut(&starter).unwrap();
        state.effort = 40.0;
        state.ceiling = 40.0;
    }
    let outs = game.outs;
    let log = game.log.len();
    let err = game
        .apply_plate_appearance(baseball_engine::harness::pitches_only(1))
        .unwrap_err();
    assert_eq!(
        err,
        GameError::LeftInPastFatigue {
            player: starter.clone()
        }
    );
    assert_eq!(game.outs, outs);
    assert_eq!(game.log.len(), log);
    assert_eq!(game.home.pitcher_slot.as_deref(), Some(starter.as_str()));

    let mut manager = ComputerManager::from_seed(3);
    let err = manager.choose(&mut game, &starter).unwrap_err();
    assert_eq!(err, GameError::LeftInPastFatigue { player: starter });
}

#[test]
fn the_state_machine_spends_effort_from_the_returned_pitches() {
    let mut ordinary = game(false);
    let pitcher = ordinary.home.pitcher_slot.clone().unwrap();
    ordinary
        .apply_plate_appearance(baseball_engine::harness::pitches_only(4))
        .unwrap();
    let spent = ordinary.home.fatigue[&pitcher].effort;
    assert!(
        (spent - 4.0).abs() < 1e-9,
        "ordinary leverage should cost 1 per pitch, spent {spent}"
    );

    let mut high = game(false);
    high.inning = 9;
    high.outs = 2;
    high.bases = Bases {
        first: Some("r1".into()),
        second: Some("r2".into()),
        third: Some("r3".into()),
    };
    high.away.lineup[0].wrc_plus = 120.0;
    let leverage = high.leverage();
    assert!((leverage - 3.03485).abs() < 1e-6, "leverage {leverage}");
    let pitcher = high.home.pitcher_slot.clone().unwrap();
    high.apply_plate_appearance(baseball_engine::harness::pitches_only(2))
        .unwrap();
    let spent = high.home.fatigue[&pitcher].effort;
    assert!(
        (spent - 2.8).abs() < 1e-9,
        "leverage 2+ and a good hitter should cost 1.40, spent {spent}"
    );

    let mut low = game(false);
    low.score.away = 8;
    low.away.lineup[0].wrc_plus = 70.0;
    let leverage = low.leverage();
    assert!(leverage <= 0.7, "leverage {leverage}");
    let pitcher = low.home.pitcher_slot.clone().unwrap();
    low.apply_plate_appearance(baseball_engine::harness::pitches_only(10))
        .unwrap();
    let spent = low.home.fatigue[&pitcher].effort;
    assert!(
        (spent - 9.0).abs() < 1e-9,
        "low leverage against a weak hitter should cost 0.90, spent {spent}"
    );
}

#[test]
fn a_regulation_game_is_nine_innings_and_pitchers_do_not_hit() {
    let mut game = game(false);
    game.apply_plate_appearance(baseball_engine::harness::solo_home_run())
        .unwrap();
    let mut saw_eighth_in_progress = false;
    let mut guard = 0;
    while !game.is_final() {
        guard += 1;
        assert!(guard < 400, "scripted game did not end");
        if game.inning == 8 {
            saw_eighth_in_progress = true;
        }
        assert!(
            game.inning <= 9,
            "a game that is not tied should not pass the 9th"
        );
        game.apply_plate_appearance(baseball_engine::harness::holding_out(&game.bases))
            .unwrap();
    }
    assert!(saw_eighth_in_progress, "the game ended before the 8th");
    assert_eq!(game.inning, 9);
    assert_eq!(game.status, Status::Final);
    assert_eq!(game.score.away, 1);
    assert_eq!(game.score.home, 0);
    assert_eq!(game.line_score.away.len(), 9);
    assert_eq!(game.line_score.home.len(), 9);

    for side in [Side::Away, Side::Home] {
        let club = game.club(side);
        assert!(club
            .lineup
            .iter()
            .any(|batter| batter.position == Position::Dh));
        for batter in &club.lineup {
            assert_ne!(batter.position, Position::Pitcher);
            assert!(club.pitchers.iter().all(|pitcher| pitcher.id != batter.id));
        }
    }
}

#[test]
fn putting_a_pitcher_in_the_order_is_rejected() {
    let mut game = game(false);
    let pitcher = game.home.pitcher_slot.clone().unwrap();
    let err = game
        .place_in_batting_order(Side::Home, 3, pitcher.clone())
        .unwrap_err();
    assert_eq!(err, GameError::PitcherDoesNotHit { player: pitcher });
    let input = game
        .plate_appearance_input(baseball_engine::PrePaCalls::default())
        .unwrap();
    assert!(game
        .home
        .pitchers
        .iter()
        .chain(&game.away.pitchers)
        .all(|pitcher| pitcher.id != input.hitter_id));
}

#[test]
fn regular_season_extras_put_the_previous_batter_on_second() {
    let mut game = game(false);
    for _ in 0..54 {
        assert_eq!(game.status, Status::InProgress);
        game.apply_plate_appearance(baseball_engine::harness::holding_out(&game.bases))
            .unwrap();
    }
    assert_eq!(game.status, Status::InProgress);
    assert_eq!(game.inning, 10);
    assert_eq!(game.half, Half::Top);
    assert_eq!(game.outs, 0);
    assert_eq!(game.away.batter_index, 0);
    let ghost = (game.away.batter_index + 8) % 9;
    assert_eq!(ghost, 8);
    assert_eq!(
        game.bases.second.as_deref(),
        Some(game.away.lineup[ghost].id.as_str())
    );
    assert!(game.bases.first.is_none());
    assert!(game.bases.third.is_none());
}

#[test]
fn postseason_extras_leave_second_empty() {
    let mut game = game(true);
    assert!(game.postseason);
    for _ in 0..54 {
        assert_eq!(game.status, Status::InProgress);
        game.apply_plate_appearance(baseball_engine::harness::holding_out(&game.bases))
            .unwrap();
    }
    assert_eq!(game.inning, 10);
    assert_eq!(game.half, Half::Top);
    assert_eq!(game.status, Status::InProgress);
    assert!(game.bases.first.is_none());
    assert!(game.bases.second.is_none());
    assert!(game.bases.third.is_none());
}

#[test]
fn three_buckets_start_with_the_lineup_in_and_the_bullpen_available() {
    let game = game(false);
    for side in [Side::Away, Side::Home] {
        let club = game.club(side);
        assert_eq!(club.in_game.len(), 10);
        assert_eq!(club.available.len(), 1);
        assert!(club.unavailable.is_empty());
        assert!(club.pitcher_slot.is_some());
    }
}

#[test]
fn defense_is_the_sum_of_the_fielders_and_the_pitcher() {
    let mut game = game(false);
    for batter in &mut game.home.lineup {
        batter.defense.rating = match batter.position {
            Position::Dh => 50.0,
            Position::Catcher => 4.0,
            _ => 1.0,
        };
    }
    let pitcher = game.home.pitcher_slot.clone().unwrap();
    game.home
        .pitchers
        .iter_mut()
        .find(|card| card.id == pitcher)
        .unwrap()
        .defense
        .rating = 2.0;
    assert!((game.defense_rating(Side::Home) - 13.0).abs() < 1e-9);
    let input = game
        .plate_appearance_input(baseball_engine::PrePaCalls::default())
        .unwrap();
    assert!((input.defense - 13.0).abs() < 1e-9);
}

#[test]
fn returned_state_is_what_the_next_plate_appearance_reads() {
    let mut game = game(false);
    game.apply_plate_appearance(baseball_engine::harness::holding_out(&game.bases))
        .unwrap();
    let saved = serde_json::to_string(&game).unwrap();
    let loaded: Game = serde_json::from_str(&saved).unwrap();
    assert_eq!(loaded, game, "the state did not survive a JSON round trip");
    assert_eq!(loaded.outs, 1);
    assert_eq!(loaded.log.len(), game.log.len());
    assert_eq!(loaded.results.len(), 1);
    assert!(loaded.last_result.is_some());
}

#[test]
fn governance_does_not_redraw() {
    let governance = Governance::new();
    let result = baseball_engine::harness::holding_out(&Bases::empty());
    let reviewed = governance.review(result.clone());
    assert_eq!(reviewed.outcome, result.outcome);
    assert_eq!(reviewed.change, result.change);
    assert_eq!(governance.redraws, 0);
}

#[test]
fn the_fixture_plays_one_regular_season_game() {
    let path = format!("{}/fixtures/game.json", env!("CARGO_MANIFEST_DIR"));
    let fixture: GameFixture = load_json(&path).unwrap();
    assert!(!fixture.postseason);
    assert!(fixture.parks.iter().any(|park| park.run_factor == 1.0));
    for team in [&fixture.away, &fixture.home] {
        assert_eq!(team.lineup.len(), 9);
        assert!(fixture
            .parks
            .iter()
            .any(|park| park.id == team.home_park_id));
        assert!(team
            .lineup
            .iter()
            .any(|batter| batter.position == Position::Dh));
        for batter in &team.lineup {
            assert!((batter.rates.sum() - 1.0).abs() < 1e-6, "{}", batter.id);
            assert!(team.pitchers.iter().all(|pitcher| pitcher.id != batter.id));
            assert_ne!(batter.position, Position::Pitcher);
        }
    }
    let home_park = fixture
        .parks
        .iter()
        .find(|park| park.id == fixture.home.home_park_id)
        .unwrap();
    assert!((home_park.run_factor - 1.0).abs() < 1e-12);

    let mut game = Game::start(fixture, 42).unwrap();
    let mut sim = Sim::from_seed(42);
    let mut manager = ComputerManager::from_seed(99);
    let governance = Governance::new();
    play_game(&mut game, &mut sim, &mut manager, &governance).unwrap();
    assert_eq!(game.status, Status::Final);
    assert!(
        game.inning >= 9 && game.inning < 30,
        "inning {}",
        game.inning
    );
    assert_eq!(governance.redraws, 0);
    let saved: Game = serde_json::from_str(&serde_json::to_string(&game).unwrap()).unwrap();
    assert_eq!(
        saved, game,
        "the final state did not survive a JSON round trip"
    );
    for result in &game.results {
        if !result.batter_completed {
            continue;
        }
        assert!(game
            .away
            .pitchers
            .iter()
            .chain(&game.home.pitchers)
            .all(|pitcher| pitcher.id != result.batter_id));
    }
}

#[test]
fn the_log_names_the_double_play_and_the_sacrifice_fly() {
    let mut game = game(false);
    let mut double_play = baseball_engine::harness::holding_out(&Bases::empty());
    double_play.outcome = PlateOutcome::GroundedIntoDoublePlay;
    double_play.change.outs_added = 2;
    game.apply_plate_appearance(double_play).unwrap();
    assert_eq!(game.outs, 2);
    assert!(game
        .log
        .last()
        .unwrap()
        .text
        .contains("grounded into a double play"));

    let mut sacrifice = baseball_engine::harness::holding_out(&Bases::empty());
    sacrifice.outcome = PlateOutcome::SacrificeFly;
    sacrifice.change.runs_scored = 1;
    game.outs = 0;
    game.apply_plate_appearance(sacrifice).unwrap();
    assert_eq!(game.score.away, 1);
    let logged = game
        .log
        .iter()
        .rev()
        .find(|entry| entry.text.contains("sacrifice fly"))
        .expect("the sacrifice fly is logged");
    assert_eq!(logged.half, Half::Top);
}

#[test]
fn a_sacrifice_fly_is_a_plate_appearance_and_not_an_at_bat() {
    assert!(!PlateOutcome::SacrificeFly.is_at_bat());
    assert!(PlateOutcome::GroundedIntoDoublePlay.is_at_bat());
    assert!(PlateOutcome::GroundOut.is_at_bat());
    assert!(PlateOutcome::FlyOut.is_at_bat());
    assert!(PlateOutcome::LineOut.is_at_bat());
}

#[test]
fn batted_ball_rates_that_do_not_sum_to_one_are_rejected() {
    let mut fixture = baseball_engine::harness::scripted_fixture(false);
    fixture.away.lineup[0].batted_balls = BattedBallRates {
        gb: 0.5,
        fb: 0.5,
        ld: 0.5,
    };
    let err = Game::start(fixture, 1).unwrap_err();
    assert!(matches!(err, GameError::InvalidFixture(msg) if msg.contains("batted-ball")));

    let mut fixture = baseball_engine::harness::scripted_fixture(false);
    fixture.home.pitchers[0].batted_balls.gb = -0.1;
    assert!(Game::start(fixture, 1).is_err());
}
