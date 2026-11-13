//! Minimal computer manager.
//!
//! When the mound is empty, the next available pitcher is taken in staff order.
//! Bunt calls are about 0.8% of plate appearances. Intentional walks are never called.
//! Steal and hit-and-run rates are 0. A call supplied by someone else is still honored by the sim.

use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};

use crate::game::{Game, GameError};
use crate::model::PrePaCalls;

pub const COMPUTER_BUNT_RATE: f64 = 0.008;
pub const COMPUTER_IBB_RATE: f64 = 0.0;
pub const COMPUTER_STEAL_RATE: f64 = 0.0;
pub const COMPUTER_HIT_AND_RUN_RATE: f64 = 0.0;

pub struct ComputerManager {
    rng: StdRng,
}

impl ComputerManager {
    pub fn from_seed(seed: u64) -> Self {
        Self {
            rng: StdRng::seed_from_u64(seed),
        }
    }

    pub fn from_entropy() -> Self {
        Self {
            rng: StdRng::from_entropy(),
        }
    }

    pub fn pre_pa_calls(&mut self) -> PrePaCalls {
        PrePaCalls {
            steal: roll(&mut self.rng, COMPUTER_STEAL_RATE),
            hit_and_run: roll(&mut self.rng, COMPUTER_HIT_AND_RUN_RATE),
            bunt: roll(&mut self.rng, COMPUTER_BUNT_RATE),
            intentional_walk: roll(&mut self.rng, COMPUTER_IBB_RATE),
            infield_in: false,
        }
    }

    pub fn assign_next(&mut self, game: &mut Game) -> Result<(), GameError> {
        let side = game.fielding_side();
        let id = {
            let club = game.club(side);
            club.pitchers
                .iter()
                .find(|card| club.available.iter().any(|id| id == &card.id))
                .map(|card| card.id.clone())
        };
        let id = id.ok_or(GameError::NoPitcherAvailable { team: side })?;
        game.seat_pitcher(&id, &mut self.rng)
    }

    pub fn choose(&mut self, game: &mut Game, player: &str) -> Result<(), GameError> {
        game.seat_pitcher(player, &mut self.rng)
    }
}

fn roll(rng: &mut StdRng, rate: f64) -> bool {
    rate > 0.0 && rng.gen::<f64>() < rate
}
