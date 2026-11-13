//! Stateless at-bat simulator.
//!
//! Same inputs do not have to produce the same result. Nothing in here is stored.
//! A bunt or an intentional walk is resolved only when that call is present.
//! A ball-in-play out is a ground out, fly out, or line out, drawn from the batted-ball mix,
//! and runners move by the rules on `advance_on_out`.

use rand::rngs::StdRng;
use rand::seq::SliceRandom;
use rand::{Rng, SeedableRng};

use crate::model::{
    Base, BaseOutRunChange, BaserunningEvent, Bases, BattedBallRates, Count, Fielding, HitterRates,
    PaInput, PaResult, Pitch, PitchKind, PitcherRates, PlateOutcome, PlayerId, Running,
};

/// League line used as the odds-ratio baseline, per plate appearance.
/// `h` is hits that are not home runs.
pub const LEAGUE_K: f64 = 0.226;
pub const LEAGUE_BB: f64 = 0.084;
pub const LEAGUE_HBP: f64 = 0.011;
pub const LEAGUE_HR: f64 = 0.031;
pub const LEAGUE_H: f64 = 0.192;

/// League batted-ball mix, as shares of batted balls. The log5 baseline and the default card.
pub const LEAGUE_GB: f64 = 0.43;
pub const LEAGUE_FB: f64 = 0.36;
pub const LEAGUE_LD: f64 = 0.21;

/// Hit probability moved into a ball-in-play out, per point of defense, per plate appearance.
pub const DEFENSE_HIT_DELTA: f64 = 0.002;

/// Chance a runner takes one extra base at league speed, or when his speed or the league's is not given.
pub const EXTRA_BASE_RATE: f64 = 0.25;
/// Bounds on the speed-scaled extra-base chance.
pub const EXTRA_BASE_MIN: f64 = 0.05;
pub const EXTRA_BASE_MAX: f64 = 0.60;

pub const BUNT_HIT_RATE: f64 = 0.15;
pub const BUNT_SAC_RATE: f64 = 0.60;
/// Steal success for a runner without a steal-success rating.
pub const STEAL_SUCCESS_RATE: f64 = 0.75;
pub const HIT_AND_RUN_K_KEEP: f64 = 0.5;

/// Ground out, runner on first, fewer than two outs: chance of a double play.
/// Set so league-average games turn two on about 10% of double-play opportunities.
pub const DP_RATE: f64 = 0.52;
/// Ground out, fewer than two outs: chance an unforced runner on third scores.
pub const GB_SCORE_FROM_THIRD: f64 = 0.50;
/// Ground out, fewer than two outs: chance an unforced runner on second takes third.
pub const GB_SECOND_TO_THIRD: f64 = 0.50;
/// Fly out, fewer than two outs: chance the runner on third scores on a sacrifice fly.
pub const SF_RATE: f64 = 0.60;
/// Fly out, fewer than two outs: chance the runner on second takes third.
pub const FLY_SECOND_TO_THIRD: f64 = 0.20;
/// Infield in: share of ground outs that get through for a single.
pub const INFIELD_IN_SINGLE_SHIFT: f64 = 0.10;

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct OutcomeProbs {
    pub k: f64,
    pub bb: f64,
    pub hbp: f64,
    pub single: f64,
    pub double: f64,
    pub triple: f64,
    pub hr: f64,
    pub bip_out: f64,
}

impl OutcomeProbs {
    pub fn sum(&self) -> f64 {
        self.k
            + self.bb
            + self.hbp
            + self.single
            + self.double
            + self.triple
            + self.hr
            + self.bip_out
    }

    pub fn non_hr_hits(&self) -> f64 {
        self.single + self.double + self.triple
    }

    pub fn batting_average(&self) -> f64 {
        let hits = self.non_hr_hits() + self.hr;
        let at_bats = hits + self.k + self.bip_out;
        if at_bats == 0.0 {
            0.0
        } else {
            hits / at_bats
        }
    }
}

pub fn card_batting_average(rates: &HitterRates) -> f64 {
    let hits = rates.hits();
    let at_bats = 1.0 - rates.bb - rates.hbp;
    if at_bats <= 0.0 {
        0.0
    } else {
        hits / at_bats
    }
}

fn odds(rate: f64) -> f64 {
    if rate <= 0.0 {
        return 0.0;
    }
    if rate >= 1.0 {
        return 1.0e12;
    }
    rate / (1.0 - rate)
}

/// Odds-ratio matchup. A pitcher equal to the league line returns the hitter's rate.
pub fn log5(batter: f64, pitcher: f64, league: f64) -> f64 {
    let league_odds = odds(league);
    if league_odds == 0.0 {
        return batter.clamp(0.0, 1.0);
    }
    let combined = odds(batter) * odds(pitcher) / league_odds;
    if !combined.is_finite() {
        return 1.0;
    }
    combined / (1.0 + combined)
}

/// Matchup, park, and defense. wRC+ is not an input. Weather is not an input.
pub fn outcome_probabilities(
    hitter: &HitterRates,
    pitcher: &PitcherRates,
    defense: f64,
    run_factor: f64,
) -> OutcomeProbs {
    let mut k = log5(hitter.k, pitcher.k, LEAGUE_K);
    let mut bb = log5(hitter.bb, pitcher.bb, LEAGUE_BB);
    let mut hbp = log5(hitter.hbp, pitcher.hbp, LEAGUE_HBP);
    let mut hr = log5(hitter.hr, pitcher.hr, LEAGUE_HR);
    let mut hits = log5(hitter.non_hr_hits(), pitcher.h, LEAGUE_H);

    let matched = k + bb + hbp + hr + hits;
    let mut bip = if matched >= 1.0 {
        let scale = 1.0 / matched;
        k *= scale;
        bb *= scale;
        hbp *= scale;
        hr *= scale;
        hits *= scale;
        0.0
    } else {
        1.0 - matched
    };

    // A run factor of 1 leaves the rates where they are, then the renormalize is a no-op.
    hits *= run_factor;
    hr *= run_factor;
    let scaled = k + bb + hbp + hr + hits + bip;
    if scaled > 0.0 {
        let scale = 1.0 / scaled;
        k *= scale;
        bb *= scale;
        hbp *= scale;
        hr *= scale;
        hits *= scale;
        bip *= scale;
    }

    let delta = defense * DEFENSE_HIT_DELTA;
    if delta >= 0.0 {
        let shift = delta.min(hits);
        hits -= shift;
        bip += shift;
    } else {
        let shift = (-delta).min(bip);
        hits += shift;
        bip -= shift;
    }

    let denom = hitter.non_hr_hits();
    let (single_share, double_share, triple_share) = if denom <= 1e-12 {
        (1.0, 0.0, 0.0)
    } else {
        (
            hitter.single / denom,
            hitter.double / denom,
            hitter.triple / denom,
        )
    };

    OutcomeProbs {
        k,
        bb,
        hbp,
        single: hits * single_share,
        double: hits * double_share,
        triple: hits * triple_share,
        hr,
        bip_out: bip,
    }
}

/// Ground, fly, and line shares for this matchup: log5 of each rate, rescaled to sum to 1.
pub fn batted_ball_mix(hitter: &BattedBallRates, pitcher: &BattedBallRates) -> BattedBallRates {
    let gb = log5(hitter.gb, pitcher.gb, LEAGUE_GB);
    let fb = log5(hitter.fb, pitcher.fb, LEAGUE_FB);
    let ld = log5(hitter.ld, pitcher.ld, LEAGUE_LD);
    let total = gb + fb + ld;
    if total <= 0.0 {
        return BattedBallRates::default();
    }
    BattedBallRates {
        gb: gb / total,
        fb: fb / total,
        ld: ld / total,
    }
}

/// Halve the strikeout rate and give that mass to hits and ball-in-play outs.
pub fn apply_hit_and_run(probs: &mut OutcomeProbs) {
    let removed = probs.k * (1.0 - HIT_AND_RUN_K_KEEP);
    probs.k -= removed;
    let contact = probs.non_hr_hits() + probs.bip_out;
    if contact <= 0.0 {
        probs.single += removed;
        return;
    }
    let hit_share = probs.non_hr_hits() / contact;
    let added_hits = removed * hit_share;
    probs.bip_out += removed - added_hits;
    if probs.non_hr_hits() <= 0.0 {
        probs.single += added_hits;
        return;
    }
    let single = probs.single;
    let double = probs.double;
    let triple = probs.triple;
    let denom = single + double + triple;
    probs.single += added_hits * (single / denom);
    probs.double += added_hits * (double / denom);
    probs.triple += added_hits * (triple / denom);
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StealTarget {
    Second,
    Third,
}

pub fn steal_target(bases: &Bases) -> Option<StealTarget> {
    if bases.first.is_some() && bases.second.is_none() {
        Some(StealTarget::Second)
    } else if bases.second.is_some() && bases.third.is_none() {
        Some(StealTarget::Third)
    } else {
        None
    }
}

/// The runner's steal-success rating, or `STEAL_SUCCESS_RATE` without one.
pub fn steal_success_rate(rating: Option<f64>) -> f64 {
    rating.unwrap_or(STEAL_SUCCESS_RATE)
}

/// `EXTRA_BASE_RATE * runner Spd / league Spd`, clamped to `EXTRA_BASE_MIN..=EXTRA_BASE_MAX`.
/// Without both speeds this is `EXTRA_BASE_RATE`.
pub fn extra_base_chance(runner_spd: Option<f64>, league_spd: Option<f64>) -> f64 {
    match (runner_spd, league_spd) {
        (Some(runner), Some(league)) if league > 0.0 => {
            (EXTRA_BASE_RATE * runner / league).clamp(EXTRA_BASE_MIN, EXTRA_BASE_MAX)
        }
        _ => EXTRA_BASE_RATE,
    }
}

fn steal_runner(bases: &Bases, target: StealTarget) -> Option<&PlayerId> {
    match target {
        StealTarget::Second => bases.first.as_ref(),
        StealTarget::Third => bases.second.as_ref(),
    }
}

pub fn apply_steal(bases: &Bases, target: StealTarget, success: bool) -> (Bases, BaserunningEvent) {
    let mut next = bases.clone();
    let (runner, to) = match target {
        StealTarget::Second => (next.first.take(), Base::Second),
        StealTarget::Third => (next.second.take(), Base::Third),
    };
    let runner = runner.unwrap_or_else(|| "runner".to_string());
    if success {
        match to {
            Base::Second => next.second = Some(runner.clone()),
            Base::Third => next.third = Some(runner.clone()),
            Base::First => {}
        }
        (next, BaserunningEvent::StolenBase { runner, to })
    } else {
        (next, BaserunningEvent::CaughtStealing { runner, at: to })
    }
}

#[derive(Debug, Clone, Copy)]
pub struct AdvanceOptions {
    pub take_extra_base: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Advancement {
    pub bases: Bases,
    pub outs_added: u8,
    pub runs_scored: u8,
    pub events: Vec<BaserunningEvent>,
    pub batter_completed: bool,
}

fn score(runner: PlayerId, runs: &mut u8, events: &mut Vec<BaserunningEvent>) {
    *runs += 1;
    events.push(BaserunningEvent::Scored { runner });
}

/// How runners move on a finished batter outcome. Extra-base chances are decided by the caller.
pub fn advance(
    bases: &Bases,
    batter: &str,
    outcome: PlateOutcome,
    outs_before: u8,
    options: AdvanceOptions,
) -> Advancement {
    let first = bases.first.clone();
    let second = bases.second.clone();
    let third = bases.third.clone();
    let mut events = Vec::new();
    let mut runs = 0u8;
    let mut next = Bases::empty();

    let (outs_added, batter_completed) = match outcome {
        PlateOutcome::CaughtStealing => {
            return Advancement {
                bases: bases.clone(),
                outs_added: 1,
                runs_scored: 0,
                events,
                batter_completed: false,
            };
        }
        PlateOutcome::Strikeout | PlateOutcome::BipOut | PlateOutcome::BuntOut => {
            next = bases.clone();
            (1, true)
        }
        PlateOutcome::GroundOut
        | PlateOutcome::FlyOut
        | PlateOutcome::LineOut
        | PlateOutcome::GroundedIntoDoublePlay
        | PlateOutcome::SacrificeFly => {
            return advance_on_out(
                bases,
                batter,
                outcome,
                outs_before,
                OutAdvanceOptions::default(),
            );
        }
        PlateOutcome::Walk | PlateOutcome::HitByPitch | PlateOutcome::IntentionalWalk => {
            next = bases.clone();
            if first.is_some() {
                if second.is_some() {
                    if let Some(runner) = third.clone() {
                        score(runner, &mut runs, &mut events);
                    }
                    next.third = second.clone();
                }
                next.second = first.clone();
            }
            next.first = Some(batter.to_string());
            (0, true)
        }
        PlateOutcome::Single | PlateOutcome::BuntSingle => {
            if let Some(runner) = third.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = second.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = first.clone() {
                if options.take_extra_base {
                    next.third = Some(runner.clone());
                    events.push(BaserunningEvent::TookExtraBase {
                        runner,
                        to: Base::Third,
                    });
                } else {
                    next.second = Some(runner);
                }
            }
            next.first = Some(batter.to_string());
            (0, true)
        }
        PlateOutcome::Double => {
            if let Some(runner) = third.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = second.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = first.clone() {
                if options.take_extra_base {
                    score(runner, &mut runs, &mut events);
                } else {
                    next.third = Some(runner);
                }
            }
            next.second = Some(batter.to_string());
            (0, true)
        }
        PlateOutcome::Triple => {
            if let Some(runner) = third.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = second.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = first.clone() {
                score(runner, &mut runs, &mut events);
            }
            next.third = Some(batter.to_string());
            (0, true)
        }
        PlateOutcome::HomeRun => {
            if let Some(runner) = third.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = second.clone() {
                score(runner, &mut runs, &mut events);
            }
            if let Some(runner) = first.clone() {
                score(runner, &mut runs, &mut events);
            }
            score(batter.to_string(), &mut runs, &mut events);
            (0, true)
        }
        PlateOutcome::BuntSacrifice => {
            if outs_before >= 2 || !bases.any() {
                next = bases.clone();
            } else {
                if let Some(runner) = third.clone() {
                    score(runner, &mut runs, &mut events);
                }
                next.third = second.clone();
                next.second = first.clone();
            }
            (1, true)
        }
    };

    Advancement {
        bases: next,
        outs_added,
        runs_scored: runs,
        events,
        batter_completed,
    }
}

/// Chances the caller already rolled for runners on a batted-ball out.
#[derive(Debug, Clone, Copy, Default)]
pub struct OutAdvanceOptions {
    /// An unforced runner on third scores on a ground out.
    pub score_from_third: bool,
    /// The runner on second takes third on a ground out or a fly out, when third is open.
    pub second_to_third: bool,
    /// The infield is in: the runner on third does not score on a ground out.
    pub infield_in: bool,
}

/// How runners move on a ground out, fly out, line out, double play, or sacrifice fly.
///
/// With two outs the out ends the inning and nobody moves. A double play removes the
/// runner from first. A sacrifice fly scores the runner from third.
pub fn advance_on_out(
    bases: &Bases,
    batter: &str,
    outcome: PlateOutcome,
    outs_before: u8,
    options: OutAdvanceOptions,
) -> Advancement {
    let mut next = bases.clone();
    let mut events = Vec::new();
    let mut runs = 0u8;
    let mut outs_added = 1u8;

    if outs_before < 2 {
        match outcome {
            PlateOutcome::GroundedIntoDoublePlay => {
                next.first = None;
                outs_added = 2;
                if outs_before == 0 {
                    if !options.infield_in {
                        if let Some(runner) = next.third.take() {
                            score(runner, &mut runs, &mut events);
                        }
                    }
                    move_second_to_open_third(&mut next);
                }
            }
            PlateOutcome::GroundOut => {
                let forced_to_second = bases.first.is_some();
                let forced_to_third = forced_to_second && bases.second.is_some();
                let forced_home = forced_to_third && bases.third.is_some();
                if forced_home && options.infield_in {
                    // The play goes home: the runner from third is out and the batter is on first.
                    next.third = next.second.take();
                    next.second = next.first.take();
                    next.first = Some(batter.to_string());
                } else {
                    if forced_home || (options.score_from_third && !options.infield_in) {
                        if let Some(runner) = next.third.take() {
                            score(runner, &mut runs, &mut events);
                        }
                    }
                    if forced_to_third || options.second_to_third {
                        move_second_to_open_third(&mut next);
                    }
                    if forced_to_second {
                        next.second = next.first.take();
                    }
                }
            }
            PlateOutcome::SacrificeFly => {
                if let Some(runner) = next.third.take() {
                    score(runner, &mut runs, &mut events);
                }
                if options.second_to_third {
                    move_second_to_open_third(&mut next);
                }
            }
            PlateOutcome::FlyOut if options.second_to_third => {
                move_second_to_open_third(&mut next);
            }
            _ => {}
        }
    }

    Advancement {
        bases: next,
        outs_added,
        runs_scored: runs,
        events,
        batter_completed: true,
    }
}

fn move_second_to_open_third(bases: &mut Bases) {
    if bases.third.is_none() {
        bases.third = bases.second.take();
    }
}

pub struct Sim {
    rng: StdRng,
}

impl Sim {
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

    pub fn resolve(&mut self, input: &PaInput) -> PaResult {
        // Received and unused. wRC+ feeds fatigue in the state machine. Weather has no effect.
        // Fatigue is part of the situation and does not change the draw.
        let _unused = (
            input.wrc_plus,
            input.situation.pitcher_fatigue,
            input.situation.pitcher_ceiling,
            input.weather.as_deref(),
            input.situation.postseason,
        );

        let mut bases = input.situation.bases.clone();
        let mut events = Vec::new();
        let mut outs_from_running = 0u8;

        if input.calls.steal && !input.calls.hit_and_run {
            if let Some(target) = steal_target(&bases) {
                let rating = steal_runner(&bases, target)
                    .and_then(|runner| input.running.runners.for_runner(runner))
                    .and_then(|rating| rating.steal_success);
                let success = self.rng.gen::<f64>() < steal_success_rate(rating);
                let (next, event) = apply_steal(&bases, target, success);
                bases = next;
                let caught = !success;
                events.push(event);
                if caught {
                    outs_from_running = 1;
                    if input.situation.outs + outs_from_running >= 3 {
                        return self.package(
                            input,
                            PlateOutcome::CaughtStealing,
                            Advancement {
                                bases,
                                outs_added: outs_from_running,
                                runs_scored: 0,
                                events,
                                batter_completed: false,
                            },
                        );
                    }
                }
            }
        }

        if input.calls.intentional_walk {
            let adv = advance(
                &bases,
                &input.hitter_id,
                PlateOutcome::IntentionalWalk,
                input.situation.outs + outs_from_running,
                AdvanceOptions {
                    take_extra_base: false,
                },
            );
            return self.package(
                input,
                PlateOutcome::IntentionalWalk,
                merge(outs_from_running, events, adv),
            );
        }

        if input.calls.bunt {
            let outcome = self.draw_bunt(&bases, input.situation.outs + outs_from_running);
            let adv = advance(
                &bases,
                &input.hitter_id,
                outcome,
                input.situation.outs + outs_from_running,
                AdvanceOptions {
                    take_extra_base: false,
                },
            );
            return self.package(input, outcome, merge(outs_from_running, events, adv));
        }

        let mut probs = outcome_probabilities(
            &input.rates,
            &input.pitcher,
            input.defense,
            input.park.run_factor,
        );
        if input.calls.hit_and_run && input.situation.bases.first.is_some() {
            apply_hit_and_run(&mut probs);
        }
        let mut outcome = self.draw_outcome(&probs);
        if outcome == PlateOutcome::BipOut {
            let outs = input.situation.outs + outs_from_running;
            let infield_in = input.calls.infield_in && bases.third.is_some() && outs < 2;
            let mix = batted_ball_mix(&input.hitter_batted_balls, &input.pitcher_batted_balls);
            let kind = self.draw_batted_ball_out(&mix);
            if kind == PlateOutcome::GroundOut
                && infield_in
                && self.rng.gen::<f64>() < INFIELD_IN_SINGLE_SHIFT
            {
                outcome = PlateOutcome::Single;
            } else {
                let (out, options) = self.roll_runners_on_out(kind, &bases, outs, infield_in);
                let adv = advance_on_out(&bases, &input.hitter_id, out, outs, options);
                return self.package(input, out, merge(outs_from_running, events, adv));
            }
        }
        let take_extra =
            self.take_extra_base(outcome, &bases, input.calls.hit_and_run, &input.running);
        let adv = advance(
            &bases,
            &input.hitter_id,
            outcome,
            input.situation.outs + outs_from_running,
            AdvanceOptions {
                take_extra_base: take_extra,
            },
        );
        self.package(input, outcome, merge(outs_from_running, events, adv))
    }

    fn take_extra_base(
        &mut self,
        outcome: PlateOutcome,
        bases: &Bases,
        hit_and_run: bool,
        running: &Running,
    ) -> bool {
        let chance = matches!(
            outcome,
            PlateOutcome::Single | PlateOutcome::Double | PlateOutcome::BuntSingle
        ) && bases.first.is_some();
        if !chance {
            return false;
        }
        if hit_and_run && matches!(outcome, PlateOutcome::Single | PlateOutcome::BuntSingle) {
            return true;
        }
        let runner_spd = bases
            .first
            .as_deref()
            .and_then(|runner| running.runners.for_runner(runner))
            .and_then(|rating| rating.spd);
        self.rng.gen::<f64>() < extra_base_chance(runner_spd, running.league_spd)
    }

    fn draw_batted_ball_out(&mut self, mix: &BattedBallRates) -> PlateOutcome {
        let roll = self.rng.gen::<f64>();
        if roll < mix.gb {
            PlateOutcome::GroundOut
        } else if roll < mix.gb + mix.fb {
            PlateOutcome::FlyOut
        } else {
            PlateOutcome::LineOut
        }
    }

    /// Decide the double play, the sacrifice fly, and which unforced runners move. With two outs nothing is rolled.
    fn roll_runners_on_out(
        &mut self,
        kind: PlateOutcome,
        bases: &Bases,
        outs: u8,
        infield_in: bool,
    ) -> (PlateOutcome, OutAdvanceOptions) {
        let mut options = OutAdvanceOptions {
            infield_in,
            ..OutAdvanceOptions::default()
        };
        if outs >= 2 {
            return (kind, options);
        }
        match kind {
            PlateOutcome::GroundOut => {
                if bases.first.is_some() {
                    if self.rng.gen::<f64>() < DP_RATE {
                        return (PlateOutcome::GroundedIntoDoublePlay, options);
                    }
                    let third_forced = bases.second.is_some();
                    if bases.third.is_some() && !third_forced && !infield_in {
                        options.score_from_third = self.rng.gen::<f64>() < GB_SCORE_FROM_THIRD;
                    }
                    return (kind, options);
                }
                if bases.third.is_some() && !infield_in {
                    options.score_from_third = self.rng.gen::<f64>() < GB_SCORE_FROM_THIRD;
                }
                if bases.second.is_some() {
                    options.second_to_third = self.rng.gen::<f64>() < GB_SECOND_TO_THIRD;
                }
                (kind, options)
            }
            PlateOutcome::FlyOut => {
                let mut out = kind;
                if bases.third.is_some() && self.rng.gen::<f64>() < SF_RATE {
                    out = PlateOutcome::SacrificeFly;
                }
                if bases.second.is_some() {
                    options.second_to_third = self.rng.gen::<f64>() < FLY_SECOND_TO_THIRD;
                }
                (out, options)
            }
            _ => (kind, options),
        }
    }

    fn draw_bunt(&mut self, bases: &Bases, outs: u8) -> PlateOutcome {
        let roll = self.rng.gen::<f64>();
        if roll < BUNT_HIT_RATE {
            PlateOutcome::BuntSingle
        } else if roll < BUNT_HIT_RATE + BUNT_SAC_RATE && outs < 2 && bases.any() {
            PlateOutcome::BuntSacrifice
        } else {
            PlateOutcome::BuntOut
        }
    }

    fn draw_outcome(&mut self, probs: &OutcomeProbs) -> PlateOutcome {
        let roll = self.rng.gen::<f64>();
        let table = [
            (PlateOutcome::Strikeout, probs.k),
            (PlateOutcome::Walk, probs.bb),
            (PlateOutcome::HitByPitch, probs.hbp),
            (PlateOutcome::Single, probs.single),
            (PlateOutcome::Double, probs.double),
            (PlateOutcome::Triple, probs.triple),
            (PlateOutcome::HomeRun, probs.hr),
            (PlateOutcome::BipOut, probs.bip_out),
        ];
        let mut cursor = 0.0;
        for (outcome, probability) in table {
            cursor += probability;
            if roll < cursor {
                return outcome;
            }
        }
        PlateOutcome::BipOut
    }

    fn package(&mut self, input: &PaInput, outcome: PlateOutcome, adv: Advancement) -> PaResult {
        let (pitches, count) = self.pitches_for(outcome);
        let in_play = matches!(
            outcome,
            PlateOutcome::Single
                | PlateOutcome::Double
                | PlateOutcome::Triple
                | PlateOutcome::HomeRun
                | PlateOutcome::BipOut
                | PlateOutcome::GroundOut
                | PlateOutcome::FlyOut
                | PlateOutcome::LineOut
                | PlateOutcome::GroundedIntoDoublePlay
                | PlateOutcome::SacrificeFly
                | PlateOutcome::BuntSingle
                | PlateOutcome::BuntOut
                | PlateOutcome::BuntSacrifice
        );
        PaResult {
            batter_id: input.hitter_id.clone(),
            pitcher_id: input.pitcher_id.clone(),
            outcome,
            batter_completed: adv.batter_completed,
            change: BaseOutRunChange {
                outs_added: adv.outs_added,
                runs_scored: adv.runs_scored,
                bases: adv.bases,
            },
            pitches,
            count,
            baserunning: adv.events,
            fielding: Fielding {
                rating: input.defense,
                in_play,
            },
        }
    }

    fn pitches_for(&mut self, outcome: PlateOutcome) -> (Vec<Pitch>, Count) {
        match outcome {
            PlateOutcome::IntentionalWalk => four_balls(),
            PlateOutcome::Strikeout => {
                let balls = self.rng.gen_range(0..4);
                self.sequence(balls, 2, true, PitchKind::SwingingStrike)
            }
            PlateOutcome::Walk => {
                let strikes = self.rng.gen_range(0..3);
                self.sequence(3, strikes, true, PitchKind::Ball)
            }
            PlateOutcome::HitByPitch => {
                let balls = self.rng.gen_range(0..4);
                let strikes = self.rng.gen_range(0..3);
                self.sequence(balls, strikes, true, PitchKind::HitByPitch)
            }
            PlateOutcome::CaughtStealing => {
                let kind = if self.rng.gen_bool(0.5) {
                    PitchKind::Ball
                } else {
                    PitchKind::CalledStrike
                };
                self.sequence(0, 0, false, kind)
            }
            _ => {
                let balls = self.rng.gen_range(0..4);
                let strikes = self.rng.gen_range(0..3);
                self.sequence(balls, strikes, true, PitchKind::InPlay)
            }
        }
    }

    fn sequence(
        &mut self,
        balls: u8,
        strikes: u8,
        fouls_at_two_strikes: bool,
        final_kind: PitchKind,
    ) -> (Vec<Pitch>, Count) {
        let mut kinds = Vec::new();
        kinds.extend(std::iter::repeat(PitchKind::Ball).take(balls as usize));
        kinds.extend(std::iter::repeat(PitchKind::CalledStrike).take(strikes as usize));
        kinds.shuffle(&mut self.rng);
        let mut built = CountBuilder::default();
        for kind in kinds {
            built.push(kind);
        }
        if fouls_at_two_strikes && built.strikes >= 2 {
            let fouls = self.rng.gen_range(0..3);
            for _ in 0..fouls {
                built.push(PitchKind::Foul);
            }
        }
        built.push(final_kind);
        built.finish()
    }
}

fn four_balls() -> (Vec<Pitch>, Count) {
    let mut built = CountBuilder::default();
    for _ in 0..4 {
        built.push(PitchKind::Ball);
    }
    built.finish()
}

fn merge(outs_before: u8, mut earlier: Vec<BaserunningEvent>, adv: Advancement) -> Advancement {
    earlier.extend(adv.events);
    Advancement {
        bases: adv.bases,
        outs_added: outs_before + adv.outs_added,
        runs_scored: adv.runs_scored,
        events: earlier,
        batter_completed: adv.batter_completed,
    }
}

#[derive(Default)]
struct CountBuilder {
    balls: u8,
    strikes: u8,
    pitches: Vec<Pitch>,
}

impl CountBuilder {
    fn push(&mut self, kind: PitchKind) {
        match kind {
            PitchKind::Ball => self.balls = (self.balls + 1).min(4),
            PitchKind::CalledStrike | PitchKind::SwingingStrike => {
                self.strikes = (self.strikes + 1).min(3);
            }
            PitchKind::Foul => {
                if self.strikes < 2 {
                    self.strikes += 1;
                }
            }
            PitchKind::InPlay | PitchKind::HitByPitch => {}
        }
        self.pitches.push(Pitch {
            kind,
            balls: self.balls,
            strikes: self.strikes,
        });
    }

    fn finish(self) -> (Vec<Pitch>, Count) {
        let count = self
            .pitches
            .last()
            .map(|pitch| Count {
                balls: pitch.balls,
                strikes: pitch.strikes,
            })
            .unwrap_or_default();
        (self.pitches, count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{BaseRunners, Half, Park, PrePaCalls, RunnerRating, Running, Situation};

    fn average_pitcher() -> PitcherRates {
        PitcherRates {
            k: LEAGUE_K,
            bb: LEAGUE_BB,
            hbp: LEAGUE_HBP,
            hr: LEAGUE_HR,
            h: LEAGUE_H,
        }
    }

    fn stub_300() -> HitterRates {
        HitterRates {
            k: 0.180,
            bb: 0.080,
            hbp: 0.010,
            single: 0.182,
            double: 0.050,
            triple: 0.006,
            hr: 0.035,
            bip_out: 0.457,
        }
    }

    #[test]
    fn league_pitcher_returns_the_hitter_card() {
        let hitter = stub_300();
        let probs = outcome_probabilities(&hitter, &average_pitcher(), 0.0, 1.0);
        assert!((probs.sum() - 1.0).abs() < 1e-9);
        assert!((probs.k - hitter.k).abs() < 1e-9);
        assert!((probs.bb - hitter.bb).abs() < 1e-9);
        assert!((probs.hbp - hitter.hbp).abs() < 1e-9);
        assert!((probs.single - hitter.single).abs() < 1e-9);
        assert!((probs.double - hitter.double).abs() < 1e-9);
        assert!((probs.triple - hitter.triple).abs() < 1e-9);
        assert!((probs.hr - hitter.hr).abs() < 1e-9);
        assert!((probs.bip_out - hitter.bip_out).abs() < 1e-9);
        assert!((probs.batting_average() - 0.300).abs() < 1e-9);
        assert!((card_batting_average(&hitter) - 0.300).abs() < 1e-9);
    }

    #[test]
    fn defense_moves_hits_and_outs_in_the_stated_direction() {
        let hitter = stub_300();
        let pitcher = average_pitcher();
        let even = outcome_probabilities(&hitter, &pitcher, 0.0, 1.0);
        let good = outcome_probabilities(&hitter, &pitcher, 10.0, 1.0);
        let poor = outcome_probabilities(&hitter, &pitcher, -10.0, 1.0);
        assert!(good.non_hr_hits() < even.non_hr_hits());
        assert!(good.bip_out > even.bip_out);
        assert!(poor.non_hr_hits() > even.non_hr_hits());
        assert!(poor.bip_out < even.bip_out);
        assert!((good.hr - even.hr).abs() < 1e-12);
        assert!((good.k - even.k).abs() < 1e-12);
    }

    #[test]
    fn neutral_park_is_a_no_op_and_a_higher_factor_raises_home_runs() {
        let hitter = stub_300();
        let pitcher = average_pitcher();
        let neutral = outcome_probabilities(&hitter, &pitcher, 0.0, 1.0);
        let hitter_park = outcome_probabilities(&hitter, &pitcher, 0.0, 1.2);
        assert!((neutral.hr - hitter.hr).abs() < 1e-9);
        assert!(hitter_park.hr > neutral.hr);
        assert!((hitter_park.sum() - 1.0).abs() < 1e-9);
    }

    #[test]
    fn single_with_a_runner_on_second_scores_him() {
        let bases = Bases {
            first: None,
            second: Some("r2".into()),
            third: None,
        };
        let adv = advance(
            &bases,
            "batter",
            PlateOutcome::Single,
            0,
            AdvanceOptions {
                take_extra_base: false,
            },
        );
        assert_eq!(adv.runs_scored, 1);
        assert_eq!(adv.outs_added, 0);
        assert_eq!(adv.bases.first.as_deref(), Some("batter"));
        assert!(adv.bases.second.is_none());
    }

    #[test]
    fn walk_with_the_bases_loaded_forces_one_run() {
        let bases = Bases {
            first: Some("r1".into()),
            second: Some("r2".into()),
            third: Some("r3".into()),
        };
        let adv = advance(
            &bases,
            "batter",
            PlateOutcome::Walk,
            1,
            AdvanceOptions {
                take_extra_base: false,
            },
        );
        assert_eq!(adv.runs_scored, 1);
        assert_eq!(adv.bases.first.as_deref(), Some("batter"));
        assert_eq!(adv.bases.second.as_deref(), Some("r1"));
        assert_eq!(adv.bases.third.as_deref(), Some("r2"));
    }

    #[test]
    fn walk_keeps_the_runners_it_does_not_force() {
        let options = AdvanceOptions {
            take_extra_base: false,
        };
        let corners = advance(
            &on(true, false, true),
            "batter",
            PlateOutcome::Walk,
            0,
            options,
        );
        assert_eq!(corners.runs_scored, 0);
        assert_eq!(corners.bases.first.as_deref(), Some("batter"));
        assert_eq!(corners.bases.second.as_deref(), Some("r1"));
        assert_eq!(corners.bases.third.as_deref(), Some("r3"));

        let second_and_third = advance(
            &on(false, true, true),
            "batter",
            PlateOutcome::Walk,
            0,
            options,
        );
        assert_eq!(second_and_third.runs_scored, 0);
        assert_eq!(second_and_third.bases.first.as_deref(), Some("batter"));
        assert_eq!(second_and_third.bases.second.as_deref(), Some("r2"));
        assert_eq!(second_and_third.bases.third.as_deref(), Some("r3"));
    }

    #[test]
    fn ball_in_play_out_holds_runners() {
        let bases = Bases {
            first: Some("r1".into()),
            second: None,
            third: Some("r3".into()),
        };
        let adv = advance(
            &bases,
            "batter",
            PlateOutcome::BipOut,
            0,
            AdvanceOptions {
                take_extra_base: true,
            },
        );
        assert_eq!(adv.outs_added, 1);
        assert_eq!(adv.runs_scored, 0);
        assert_eq!(adv.bases, bases);
    }

    #[test]
    fn extra_base_on_a_single_sends_the_runner_to_third() {
        let bases = Bases {
            first: Some("r1".into()),
            second: None,
            third: None,
        };
        let adv = advance(
            &bases,
            "batter",
            PlateOutcome::Single,
            0,
            AdvanceOptions {
                take_extra_base: true,
            },
        );
        assert_eq!(adv.bases.third.as_deref(), Some("r1"));
        assert_eq!(adv.bases.first.as_deref(), Some("batter"));
        assert!(adv.bases.second.is_none());
        assert!(adv
            .events
            .iter()
            .any(|event| matches!(event, BaserunningEvent::TookExtraBase { .. })));
    }

    #[test]
    fn home_run_with_the_bases_loaded_scores_four() {
        let bases = Bases {
            first: Some("r1".into()),
            second: Some("r2".into()),
            third: Some("r3".into()),
        };
        let adv = advance(
            &bases,
            "batter",
            PlateOutcome::HomeRun,
            2,
            AdvanceOptions {
                take_extra_base: false,
            },
        );
        assert_eq!(adv.runs_scored, 4);
        assert_eq!(adv.bases, Bases::empty());
    }

    #[test]
    fn intentional_walk_is_four_balls_and_only_when_called() {
        let input = sample_input(false);
        let mut called = input.clone();
        called.calls.intentional_walk = true;
        let mut sim = Sim::from_seed(7);
        let result = sim.resolve(&called);
        assert_eq!(result.outcome, PlateOutcome::IntentionalWalk);
        assert_eq!(result.pitches.len(), 4);
        assert!(result
            .pitches
            .iter()
            .all(|pitch| pitch.kind == PitchKind::Ball));
        assert_eq!(
            result.count,
            Count {
                balls: 4,
                strikes: 0
            }
        );

        let mut quiet = Sim::from_seed(7);
        let other = quiet.resolve(&input);
        assert_ne!(other.outcome, PlateOutcome::IntentionalWalk);
    }

    #[test]
    fn bunt_without_a_call_does_not_happen() {
        let input = sample_input(false);
        let mut sim = Sim::from_seed(11);
        for _ in 0..200 {
            let result = sim.resolve(&input);
            assert!(!matches!(
                result.outcome,
                PlateOutcome::BuntOut | PlateOutcome::BuntSingle | PlateOutcome::BuntSacrifice
            ));
        }
    }

    trait Place {
        fn with_second(self, runner: &str) -> Self;
        fn with_third(self, runner: &str) -> Self;
    }

    impl Place for Bases {
        fn with_second(mut self, runner: &str) -> Self {
            self.second = Some(runner.to_string());
            self
        }

        fn with_third(mut self, runner: &str) -> Self {
            self.third = Some(runner.to_string());
            self
        }
    }

    fn on(first: bool, second: bool, third: bool) -> Bases {
        Bases {
            first: first.then(|| "r1".to_string()),
            second: second.then(|| "r2".to_string()),
            third: third.then(|| "r3".to_string()),
        }
    }

    fn out(
        outcome: PlateOutcome,
        bases: &Bases,
        outs: u8,
        options: OutAdvanceOptions,
    ) -> Advancement {
        advance_on_out(bases, "batter", outcome, outs, options)
    }

    fn rolled(score_from_third: bool, second_to_third: bool) -> OutAdvanceOptions {
        OutAdvanceOptions {
            score_from_third,
            second_to_third,
            infield_in: false,
        }
    }

    #[test]
    fn runner_constants_match_the_stated_defaults() {
        assert_eq!(GB_SCORE_FROM_THIRD, 0.50);
        assert_eq!(GB_SECOND_TO_THIRD, 0.50);
        assert_eq!(SF_RATE, 0.60);
        assert_eq!(FLY_SECOND_TO_THIRD, 0.20);
        assert_eq!(INFIELD_IN_SINGLE_SHIFT, 0.10);
        assert!((LEAGUE_GB + LEAGUE_FB + LEAGUE_LD - 1.0).abs() < 1e-12);
    }

    #[test]
    fn double_play_with_none_out_moves_the_other_runners_up_one() {
        let adv = out(
            PlateOutcome::GroundedIntoDoublePlay,
            &on(true, true, true),
            0,
            OutAdvanceOptions::default(),
        );
        assert_eq!(adv.outs_added, 2);
        assert_eq!(adv.runs_scored, 1);
        assert_eq!(adv.bases, on(false, false, false).with_third("r2"));
        assert!(adv.batter_completed);
        assert!(adv.events.contains(&BaserunningEvent::Scored {
            runner: "r3".into()
        }));
    }

    #[test]
    fn double_play_with_one_out_ends_the_inning_and_nobody_scores() {
        let adv = out(
            PlateOutcome::GroundedIntoDoublePlay,
            &on(true, false, true),
            1,
            OutAdvanceOptions::default(),
        );
        assert_eq!(adv.outs_added, 2);
        assert_eq!(adv.runs_scored, 0);
        assert!(adv.events.is_empty());
    }

    #[test]
    fn ground_out_forces_every_runner_up_with_the_bases_loaded() {
        let adv = out(
            PlateOutcome::GroundOut,
            &on(true, true, true),
            0,
            rolled(false, false),
        );
        assert_eq!(adv.outs_added, 1);
        assert_eq!(adv.runs_scored, 1);
        assert_eq!(
            adv.bases,
            on(false, true, true).with_second("r1").with_third("r2")
        );
    }

    #[test]
    fn ground_out_forces_the_runner_from_first_and_leaves_the_unforced_runner_on_third_to_the_roll()
    {
        let held = out(
            PlateOutcome::GroundOut,
            &on(true, false, true),
            0,
            rolled(false, false),
        );
        assert_eq!(held.runs_scored, 0);
        assert_eq!(held.bases, on(false, false, true).with_second("r1"));

        let scored = out(
            PlateOutcome::GroundOut,
            &on(true, false, true),
            1,
            rolled(true, false),
        );
        assert_eq!(scored.runs_scored, 1);
        assert_eq!(scored.bases, on(false, false, false).with_second("r1"));
    }

    #[test]
    fn ground_out_moves_an_unforced_runner_from_second_only_on_the_roll_and_only_to_an_open_base() {
        let moved = out(
            PlateOutcome::GroundOut,
            &on(false, true, false),
            0,
            rolled(false, true),
        );
        assert_eq!(moved.bases, on(false, false, false).with_third("r2"));
        assert_eq!(moved.runs_scored, 0);

        let stayed = out(
            PlateOutcome::GroundOut,
            &on(false, true, false),
            0,
            rolled(false, false),
        );
        assert_eq!(stayed.bases, on(false, true, false));

        let blocked = out(
            PlateOutcome::GroundOut,
            &on(false, true, true),
            0,
            rolled(false, true),
        );
        assert_eq!(blocked.bases, on(false, true, true));

        let behind_the_run = out(
            PlateOutcome::GroundOut,
            &on(false, true, true),
            0,
            rolled(true, true),
        );
        assert_eq!(behind_the_run.runs_scored, 1);
        assert_eq!(
            behind_the_run.bases,
            on(false, false, false).with_third("r2")
        );
    }

    #[test]
    fn sacrifice_fly_scores_the_runner_from_third_and_a_fly_out_holds_him() {
        let sac = out(
            PlateOutcome::SacrificeFly,
            &on(true, false, true),
            0,
            rolled(false, false),
        );
        assert_eq!(sac.outs_added, 1);
        assert_eq!(sac.runs_scored, 1);
        assert_eq!(sac.bases, on(true, false, false));

        let fly = out(
            PlateOutcome::FlyOut,
            &on(true, false, true),
            0,
            rolled(false, false),
        );
        assert_eq!(fly.runs_scored, 0);
        assert_eq!(fly.bases, on(true, false, true));
    }

    #[test]
    fn fly_out_moves_the_runner_from_second_on_the_roll() {
        let tagged = out(
            PlateOutcome::FlyOut,
            &on(false, true, false),
            1,
            rolled(false, true),
        );
        assert_eq!(tagged.bases, on(false, false, false).with_third("r2"));

        let sac = out(
            PlateOutcome::SacrificeFly,
            &on(false, true, true),
            0,
            rolled(false, true),
        );
        assert_eq!(sac.runs_scored, 1);
        assert_eq!(sac.bases, on(false, false, false).with_third("r2"));
    }

    #[test]
    fn line_out_moves_nobody() {
        let bases = on(true, true, true);
        let adv = out(PlateOutcome::LineOut, &bases, 0, rolled(true, true));
        assert_eq!(adv.outs_added, 1);
        assert_eq!(adv.runs_scored, 0);
        assert_eq!(adv.bases, bases);
    }

    #[test]
    fn with_two_outs_an_out_ends_the_inning_and_nobody_advances() {
        let bases = on(true, true, true);
        for outcome in [
            PlateOutcome::GroundOut,
            PlateOutcome::FlyOut,
            PlateOutcome::LineOut,
            PlateOutcome::SacrificeFly,
            PlateOutcome::GroundedIntoDoublePlay,
        ] {
            let adv = out(outcome, &bases, 2, rolled(true, true));
            assert_eq!(adv.outs_added, 1, "{outcome:?}");
            assert_eq!(adv.runs_scored, 0, "{outcome:?}");
            assert_eq!(adv.bases, bases, "{outcome:?}");
        }
    }

    #[test]
    fn infield_in_holds_the_runner_on_third_on_a_ground_out() {
        let options = OutAdvanceOptions {
            score_from_third: true,
            second_to_third: true,
            infield_in: true,
        };
        let held = out(PlateOutcome::GroundOut, &on(false, true, true), 0, options);
        assert_eq!(held.runs_scored, 0);
        assert_eq!(held.bases, on(false, true, true));

        let double_play = out(
            PlateOutcome::GroundedIntoDoublePlay,
            &on(true, true, true),
            0,
            options,
        );
        assert_eq!(double_play.runs_scored, 0);
        assert_eq!(double_play.bases, on(false, true, true));
    }

    #[test]
    fn infield_in_with_the_bases_loaded_gets_the_force_at_home() {
        let options = OutAdvanceOptions {
            infield_in: true,
            ..OutAdvanceOptions::default()
        };
        let adv = out(PlateOutcome::GroundOut, &on(true, true, true), 1, options);
        assert_eq!(adv.outs_added, 1);
        assert_eq!(adv.runs_scored, 0);
        assert_eq!(
            adv.bases,
            Bases {
                first: Some("batter".into()),
                second: Some("r1".into()),
                third: Some("r2".into()),
            }
        );
    }

    #[test]
    fn batted_ball_mix_is_log5_against_the_league() {
        let hitter = BattedBallRates {
            gb: 0.50,
            fb: 0.30,
            ld: 0.20,
        };
        let league = BattedBallRates::default();
        let even = batted_ball_mix(&hitter, &league);
        assert!((even.gb - hitter.gb).abs() < 1e-9);
        assert!((even.fb - hitter.fb).abs() < 1e-9);
        assert!((even.ld - hitter.ld).abs() < 1e-9);

        let sinkerballer = BattedBallRates {
            gb: 0.55,
            fb: 0.27,
            ld: 0.18,
        };
        let mix = batted_ball_mix(&hitter, &sinkerballer);
        assert!((mix.sum() - 1.0).abs() < 1e-9);
        assert!(mix.gb > hitter.gb);
        assert!(mix.fb < hitter.fb);
    }

    #[test]
    fn the_sim_never_draws_the_runner_holding_ball_in_play_out() {
        let mut input = sample_input(false);
        input.situation.bases = on(true, true, true);
        let mut sim = Sim::from_seed(17);
        for _ in 0..2_000 {
            let result = sim.resolve(&input);
            assert_ne!(result.outcome, PlateOutcome::BipOut);
        }
    }

    const LEAGUE_SPD: f64 = 4.5;

    fn rated(id: &str, steal_success: Option<f64>, spd: Option<f64>) -> RunnerRating {
        RunnerRating {
            id: id.into(),
            steal_success,
            spd,
        }
    }

    fn runner_on_first(rating: Option<RunnerRating>, league_spd: Option<f64>) -> PaInput {
        let mut input = sample_input(false);
        input.situation.bases.first = Some("r1".into());
        input.running = Running {
            runners: BaseRunners {
                first: rating,
                ..BaseRunners::default()
            },
            league_spd,
        };
        input
    }

    /// Share of singles and doubles on which the runner from first took the extra base.
    fn extra_base_share(input: &PaInput, seed: u64) -> f64 {
        let mut sim = Sim::from_seed(seed);
        let mut chances = 0u32;
        let mut taken = 0u32;
        while chances < 4_000 {
            let result = sim.resolve(input);
            if !matches!(result.outcome, PlateOutcome::Single | PlateOutcome::Double) {
                continue;
            }
            chances += 1;
            let took = match result.outcome {
                PlateOutcome::Single => result
                    .baserunning
                    .iter()
                    .any(|event| matches!(event, BaserunningEvent::TookExtraBase { .. })),
                _ => result.baserunning.iter().any(
                    |event| matches!(event, BaserunningEvent::Scored { runner } if runner == "r1"),
                ),
            };
            if took {
                taken += 1;
            }
        }
        f64::from(taken) / f64::from(chances)
    }

    /// Share of steal calls with a runner on first that ended in a stolen base.
    fn steal_share(input: &PaInput, seed: u64) -> f64 {
        let mut called = input.clone();
        called.calls.steal = true;
        let mut sim = Sim::from_seed(seed);
        let tries = 4_000;
        let stolen = (0..tries)
            .filter(|_| {
                sim.resolve(&called)
                    .baserunning
                    .iter()
                    .any(|event| matches!(event, BaserunningEvent::StolenBase { .. }))
            })
            .count();
        stolen as f64 / tries as f64
    }

    #[test]
    fn extra_base_chance_scales_with_runner_speed_over_league_speed() {
        let fast = extra_base_chance(Some(8.0), Some(LEAGUE_SPD));
        let slow = extra_base_chance(Some(2.0), Some(LEAGUE_SPD));
        assert!((fast - EXTRA_BASE_RATE * 8.0 / LEAGUE_SPD).abs() < 1e-12);
        assert!((slow - EXTRA_BASE_RATE * 2.0 / LEAGUE_SPD).abs() < 1e-12);
        assert!(
            (extra_base_chance(Some(LEAGUE_SPD), Some(LEAGUE_SPD)) - EXTRA_BASE_RATE).abs() < 1e-12
        );
    }

    #[test]
    fn extra_base_chance_is_clamped() {
        assert_eq!(EXTRA_BASE_MIN, 0.05);
        assert_eq!(EXTRA_BASE_MAX, 0.60);
        assert_eq!(
            extra_base_chance(Some(15.0), Some(LEAGUE_SPD)),
            EXTRA_BASE_MAX
        );
        assert_eq!(
            extra_base_chance(Some(0.5), Some(LEAGUE_SPD)),
            EXTRA_BASE_MIN
        );
        assert_eq!(
            extra_base_chance(Some(0.0), Some(LEAGUE_SPD)),
            EXTRA_BASE_MIN
        );
    }

    #[test]
    fn extra_base_chance_without_both_speeds_is_the_constant() {
        assert_eq!(extra_base_chance(None, None), EXTRA_BASE_RATE);
        assert_eq!(extra_base_chance(Some(8.0), None), EXTRA_BASE_RATE);
        assert_eq!(extra_base_chance(None, Some(LEAGUE_SPD)), EXTRA_BASE_RATE);
    }

    #[test]
    fn steal_success_is_the_runner_rating_or_the_constant() {
        assert_eq!(steal_success_rate(Some(0.9)), 0.9);
        assert_eq!(steal_success_rate(None), STEAL_SUCCESS_RATE);
    }

    #[test]
    fn a_fast_runner_takes_the_extra_base_more_than_a_slow_one() {
        let fast = runner_on_first(Some(rated("r1", None, Some(8.0))), Some(LEAGUE_SPD));
        let slow = runner_on_first(Some(rated("r1", None, Some(2.0))), Some(LEAGUE_SPD));
        let fast_share = extra_base_share(&fast, 31);
        let slow_share = extra_base_share(&slow, 31);
        assert!(
            (fast_share - EXTRA_BASE_RATE * 8.0 / LEAGUE_SPD).abs() < 0.03,
            "fast {fast_share}"
        );
        assert!(
            (slow_share - EXTRA_BASE_RATE * 2.0 / LEAGUE_SPD).abs() < 0.03,
            "slow {slow_share}"
        );
    }

    #[test]
    fn a_runner_without_ratings_takes_the_extra_base_at_the_constant() {
        let unrated = runner_on_first(None, Some(LEAGUE_SPD));
        let share = extra_base_share(&unrated, 32);
        assert!((share - EXTRA_BASE_RATE).abs() < 0.03, "unrated {share}");
    }

    #[test]
    fn a_rating_for_someone_else_does_not_reach_the_runner() {
        let other = runner_on_first(None, Some(LEAGUE_SPD));
        let mut misplaced = other.clone();
        misplaced.running.runners.second = Some(rated("r1-elsewhere", Some(0.0), Some(20.0)));
        assert_eq!(
            extra_base_share(&other, 33),
            extra_base_share(&misplaced, 33)
        );
    }

    #[test]
    fn a_steal_succeeds_at_the_runner_rating() {
        let burner = runner_on_first(Some(rated("r1", Some(0.92), None)), None);
        let catcher = runner_on_first(Some(rated("r1", Some(0.40), None)), None);
        assert!((steal_share(&burner, 41) - 0.92).abs() < 0.03);
        assert!((steal_share(&catcher, 41) - 0.40).abs() < 0.03);
    }

    #[test]
    fn a_steal_without_a_rating_succeeds_at_the_constant() {
        let unrated = runner_on_first(None, None);
        assert!((steal_share(&unrated, 42) - STEAL_SUCCESS_RATE).abs() < 0.03);
    }

    #[test]
    fn the_runner_stealing_third_uses_his_own_rating() {
        let mut input = sample_input(false);
        input.situation.bases.first = Some("r1".into());
        input.situation.bases.second = Some("r2".into());
        input.running.runners.first = Some(rated("r1", Some(0.0), None));
        input.running.runners.second = Some(rated("r2", Some(1.0), None));
        input.calls.steal = true;
        let mut sim = Sim::from_seed(43);
        for _ in 0..50 {
            let result = sim.resolve(&input);
            assert!(result.baserunning.contains(&BaserunningEvent::StolenBase {
                runner: "r2".into(),
                to: Base::Third,
            }));
        }
    }

    fn sample_input(intentional_walk: bool) -> PaInput {
        PaInput {
            hitter_id: "batter".into(),
            hitter_name: "Batter".into(),
            rates: stub_300(),
            wrc_plus: 140.0,
            pitcher_id: "pitcher".into(),
            pitcher_name: "Pitcher".into(),
            pitcher: average_pitcher(),
            hitter_batted_balls: BattedBallRates::default(),
            pitcher_batted_balls: BattedBallRates::default(),
            defense: 0.0,
            situation: Situation {
                inning: 1,
                half: Half::Top,
                outs: 0,
                bases: Bases::empty(),
                away_score: 0,
                home_score: 0,
                pitcher_fatigue: 10.0,
                pitcher_ceiling: 100.0,
                postseason: false,
            },
            park: Park {
                id: "neutral".into(),
                run_factor: 1.0,
            },
            weather: Some("crosswind".into()),
            calls: PrePaCalls {
                intentional_walk,
                ..PrePaCalls::default()
            },
            running: Running::default(),
        }
    }
}
