//! Drives one game from plate appearance to plate appearance.
//!
//! The state machine applies the result. The caller keeps that state. The sim keeps nothing.

use crate::game::{Game, GameError};
use crate::governance::Governance;
use crate::manager::ComputerManager;
use crate::model::{PrePaCalls, Running};
use crate::sim::Sim;

/// Resolve exactly one plate appearance.
///
/// `call` is a human choice. When it is absent, the computer manager supplies the call.
/// `running` carries the ratings of the runners on base; empty runs everyone at the league constants.
/// An empty mound is filled before this plate appearance, not instead of it.
pub fn step_plate_appearance(
    game: &mut Game,
    sim: &mut Sim,
    manager: &mut ComputerManager,
    governance: &Governance,
    call: Option<PrePaCalls>,
    running: &Running,
) -> Result<(), GameError> {
    if game.is_final() {
        return Err(GameError::GameOver);
    }
    if needs_pitcher(game) {
        manager.assign_next(game)?;
    }
    let calls = match call {
        Some(calls) => calls,
        None => manager.pre_pa_calls(),
    };
    running
        .check(&game.bases)
        .map_err(GameError::InvalidRunning)?;
    let mut input = game.plate_appearance_input(calls)?;
    input.running = running.clone();
    let result = governance.review(sim.resolve(&input));
    game.apply_plate_appearance(result)?;
    Ok(())
}

/// True when the mound is empty or its pitcher is spent, so a pitcher enters before the next plate appearance.
pub fn needs_pitcher(game: &Game) -> bool {
    let side = game.fielding_side();
    match game.club(side).pitcher_slot.as_deref() {
        None => true,
        Some(id) => game.pitcher_is_spent(side, id),
    }
}

pub fn play_game(
    game: &mut Game,
    sim: &mut Sim,
    manager: &mut ComputerManager,
    governance: &Governance,
) -> Result<(), GameError> {
    let mut guard = 0u32;
    while !game.is_final() {
        guard += 1;
        if guard > 2_000 {
            return Err(GameError::TooLong);
        }
        step_plate_appearance(game, sim, manager, governance, None, &Running::default())?;
    }
    Ok(())
}
