//! Constructors the tests use to drive the state machine with a known game.

use crate::model::{
    Bases, BattedBallRates, BatterCard, DefenseRating, FatigueProfile, GameFixture, HitterRates,
    Park, PitcherCard, PitcherRates, PitcherRole, Position, TeamFixture,
};

const POSITIONS: [Position; 9] = [
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

pub fn scripted_fixture(postseason: bool) -> GameFixture {
    GameFixture {
        postseason,
        parks: vec![Park {
            id: "neutral".into(),
            run_factor: 1.0,
        }],
        weather: None,
        away: scripted_team("away", "Visitors"),
        home: scripted_team("home", "Home"),
    }
}

fn scripted_team(id: &str, name: &str) -> TeamFixture {
    let lineup = POSITIONS
        .iter()
        .enumerate()
        .map(|(index, position)| BatterCard {
            id: format!("{id}-b{index}"),
            name: format!("{name} {index}"),
            position: *position,
            defense: DefenseRating {
                rating: 0.0,
                measured_at: *position,
            },
            wrc_plus: 100.0,
            rates: HitterRates {
                k: 0.22,
                bb: 0.08,
                hbp: 0.01,
                single: 0.15,
                double: 0.04,
                triple: 0.005,
                hr: 0.02,
                bip_out: 0.475,
            },
            batted_balls: BattedBallRates::default(),
        })
        .collect();
    let pitchers = vec![
        scripted_pitcher(&format!("{id}-sp"), "Starter", PitcherRole::Starter, 200.0),
        scripted_pitcher(&format!("{id}-rp"), "Reliever", PitcherRole::Reliever, 40.0),
    ];
    TeamFixture {
        id: id.into(),
        name: name.into(),
        home_park_id: "neutral".into(),
        lineup,
        pitchers,
    }
}

fn scripted_pitcher(id: &str, name: &str, role: PitcherRole, ppa: f64) -> PitcherCard {
    PitcherCard {
        id: id.into(),
        name: name.into(),
        defense: DefenseRating {
            rating: 0.0,
            measured_at: Position::Pitcher,
        },
        rates: PitcherRates {
            k: 0.22,
            bb: 0.08,
            hbp: 0.01,
            hr: 0.03,
            h: 0.17,
        },
        fatigue: FatigueProfile {
            role,
            age: 28,
            season_pitches_per_appearance: ppa,
            career_pitches_per_appearance: ppa,
            season_appearances: 30,
        },
        batted_balls: BattedBallRates::default(),
    }
}

pub fn holding_out(bases: &Bases) -> crate::model::PaResult {
    use crate::model::{
        BaseOutRunChange, Count, Fielding, PaResult, Pitch, PitchKind, PlateOutcome,
    };
    PaResult {
        batter_id: "script".into(),
        pitcher_id: "script".into(),
        outcome: PlateOutcome::BipOut,
        batter_completed: true,
        change: BaseOutRunChange {
            outs_added: 1,
            runs_scored: 0,
            bases: bases.clone(),
        },
        pitches: vec![Pitch {
            kind: PitchKind::InPlay,
            balls: 0,
            strikes: 0,
        }],
        count: Count::default(),
        baserunning: Vec::new(),
        fielding: Fielding {
            rating: 0.0,
            in_play: true,
        },
    }
}

pub fn solo_home_run() -> crate::model::PaResult {
    use crate::model::{
        BaseOutRunChange, Count, Fielding, PaResult, Pitch, PitchKind, PlateOutcome,
    };
    PaResult {
        batter_id: "script".into(),
        pitcher_id: "script".into(),
        outcome: PlateOutcome::HomeRun,
        batter_completed: true,
        change: BaseOutRunChange {
            outs_added: 0,
            runs_scored: 1,
            bases: Bases::empty(),
        },
        pitches: vec![Pitch {
            kind: PitchKind::InPlay,
            balls: 1,
            strikes: 1,
        }],
        count: Count {
            balls: 1,
            strikes: 1,
        },
        baserunning: Vec::new(),
        fielding: Fielding {
            rating: 0.0,
            in_play: true,
        },
    }
}

pub fn pitches_only(count: usize) -> crate::model::PaResult {
    use crate::model::{
        BaseOutRunChange, Count, Fielding, PaResult, Pitch, PitchKind, PlateOutcome,
    };
    PaResult {
        batter_id: "script".into(),
        pitcher_id: "script".into(),
        outcome: PlateOutcome::Walk,
        batter_completed: true,
        change: BaseOutRunChange {
            outs_added: 0,
            runs_scored: 0,
            bases: Bases::empty(),
        },
        pitches: (0..count)
            .map(|_| Pitch {
                kind: PitchKind::Ball,
                balls: 1,
                strikes: 0,
            })
            .collect(),
        count: Count {
            balls: 4,
            strikes: 0,
        },
        baserunning: Vec::new(),
        fielding: Fielding {
            rating: 0.0,
            in_play: false,
        },
    }
}
