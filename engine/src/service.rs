// ABOUTME: Pure functions behind the HTTP routes: open a game, step one plate appearance, read the matchup.
// ABOUTME: Each call builds its random streams from the seed it is given and keeps nothing afterward.
//! Stateless game steps.
//!
//! The caller owns the state and picks every seed. `step` builds the sim and the
//! computer manager from that seed, so the same state, call, and seed always give the
//! same plate appearance. Nothing here outlives the call.

use rand::rngs::StdRng;
use rand::SeedableRng;
use serde::Serialize;

use crate::game::{Game, GameError, PositionChange, SubstituteRole};
use crate::governance::Governance;
use crate::manager::ComputerManager;
use crate::model::{
    BatterCard, GameFixture, PaResult, PitcherCard, PlayerId, PrePaCalls, Running, Side,
};
use crate::runner::{needs_pitcher, step_plate_appearance};
use crate::sim::{outcome_probabilities, OutcomeProbs, Sim};

/// Mixed into the step seed so the computer manager's stream is not the sim's stream.
const MANAGER_SEED_MIX: u64 = 0x9E37_79B9_7F4A_7C15;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Stepped {
    pub result: PaResult,
    pub state: Game,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Matchup {
    pub batter_id: PlayerId,
    pub batter_name: String,
    pub pitcher_id: PlayerId,
    pub pitcher_name: String,
    /// True when this pitcher is not on the mound yet and enters before the plate appearance.
    pub pitcher_entering: bool,
    pub probabilities: OutcomeProbs,
}

/// Open `fixture`. The seed draws each starter's fatigue line.
pub fn start(fixture: GameFixture, seed: u64) -> Result<Game, GameError> {
    Game::start(fixture, seed)
}

/// Resolve exactly one plate appearance. `call` is a human choice; `None` lets the computer manager call it.
/// `running` carries the ratings of the runners on base; empty runs everyone at the league constants.
pub fn step(
    mut game: Game,
    call: Option<PrePaCalls>,
    seed: u64,
    running: &Running,
) -> Result<Stepped, GameError> {
    let mut sim = Sim::from_seed(seed);
    let mut manager = ComputerManager::from_seed(seed ^ MANAGER_SEED_MIX);
    let governance = Governance::new();
    step_plate_appearance(
        &mut game,
        &mut sim,
        &mut manager,
        &governance,
        call,
        running,
    )?;
    let result = game
        .last_result
        .clone()
        .expect("a plate appearance that was applied leaves its result");
    Ok(Stepped {
        result,
        state: game,
    })
}

/// A pitching change for the fielding club. The seed draws the new pitcher's fatigue line.
pub fn bring_in_pitcher(mut game: Game, card: PitcherCard, seed: u64) -> Result<Game, GameError> {
    let mut rng = StdRng::seed_from_u64(seed);
    game.bring_in_pitcher(card, &mut rng)?;
    Ok(game)
}

/// Replace one batting-order slot of `side`, entering as `role` says. Draws nothing.
pub fn substitute(
    mut game: Game,
    side: Side,
    index: usize,
    card: BatterCard,
    role: SubstituteRole,
) -> Result<Game, GameError> {
    game.substitute(side, index, card, role)?;
    Ok(game)
}

/// New fielding positions for the fielding club. Draws nothing.
pub fn set_positions(
    mut game: Game,
    side: Side,
    changes: Vec<PositionChange>,
) -> Result<Game, GameError> {
    game.set_positions(side, changes)?;
    Ok(game)
}

/// The probabilities a normal plate appearance (no call) would draw from next.
///
/// When the mound is empty or spent, this names the pitcher who will enter, as `step` does.
/// That pitcher's fatigue line is drawn on a copy and thrown away; it does not change these numbers.
pub fn matchup(game: &Game) -> Result<Matchup, GameError> {
    if game.is_final() {
        return Err(GameError::GameOver);
    }
    let mut next = game.clone();
    let pitcher_entering = needs_pitcher(&next);
    if pitcher_entering {
        ComputerManager::from_seed(0).assign_next(&mut next)?;
    }
    let input = next.plate_appearance_input(PrePaCalls::default())?;
    Ok(Matchup {
        probabilities: outcome_probabilities(
            &input.rates,
            &input.pitcher,
            input.defense,
            input.park.run_factor,
        ),
        batter_id: input.hitter_id,
        batter_name: input.hitter_name,
        pitcher_id: input.pitcher_id,
        pitcher_name: input.pitcher_name,
        pitcher_entering,
    })
}
