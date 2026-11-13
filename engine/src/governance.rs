//! Empty governance stub.
//!
//! It can see a plate-appearance result. No rule is defined, so it does not redraw.

use crate::model::PaResult;

#[derive(Debug, Default)]
pub struct Governance {
    pub redraws: u32,
}

impl Governance {
    pub fn new() -> Self {
        Self { redraws: 0 }
    }

    pub fn review(&self, result: PaResult) -> PaResult {
        result
    }
}
