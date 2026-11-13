//! One regular-season baseball game.
//!
//! The library is the state machine, the stateless at-bat simulator, and a minimal
//! computer manager. `play` reads a fixture and plays one game. `serve` answers
//! stateless HTTP requests: the caller sends the whole game state and a seed, and
//! gets back one plate appearance and the next state.

pub mod fatigue;
pub mod game;
pub mod governance;
pub mod harness;
pub mod http;
pub mod manager;
pub mod model;
pub mod runner;
pub mod service;
pub mod sim;

pub use fatigue::{base_ceiling, draw_window, effort_per_pitch};
pub use game::{Game, GameError};
pub use governance::Governance;
pub use http::router;
pub use manager::{
    ComputerManager, COMPUTER_BUNT_RATE, COMPUTER_HIT_AND_RUN_RATE, COMPUTER_IBB_RATE,
    COMPUTER_STEAL_RATE,
};
pub use model::*;
pub use runner::play_game;
pub use sim::{
    advance_on_out, batted_ball_mix, OutAdvanceOptions, DP_RATE, FLY_SECOND_TO_THIRD,
    GB_SCORE_FROM_THIRD, GB_SECOND_TO_THIRD, INFIELD_IN_SINGLE_SHIFT, LEAGUE_FB, LEAGUE_GB,
    LEAGUE_LD, SF_RATE,
};
pub use sim::{
    card_batting_average, outcome_probabilities, OutcomeProbs, Sim, DEFENSE_HIT_DELTA,
    EXTRA_BASE_RATE, LEAGUE_BB, LEAGUE_H, LEAGUE_HBP, LEAGUE_HR, LEAGUE_K,
};
