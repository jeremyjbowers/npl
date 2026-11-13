//! Pitcher fatigue. The state machine spends effort. The sim only receives the current total.
//!
//! The numbers are the league-editor defaults from the project context. A weak hitter is under 85 wRC+.

use rand::Rng;

use crate::model::{FatigueProfile, PitcherRole};

pub const STARTER_PRIOR_PITCHES: f64 = 95.0;
pub const RELIEVER_PRIOR_PITCHES: f64 = 18.0;
pub const FULL_SAMPLE_APPEARANCES: f64 = 10.0;
pub const STARTER_CEILING_MULT: f64 = 1.18;
pub const RELIEVER_CEILING_MULT: f64 = 1.10;
pub const YOUNG_DRAW_PITCHES: i32 = 6;
pub const OLD_DOWNSIDE: f64 = 0.14;
pub const OLD_UPSIDE: f64 = 0.04;
pub const WEAK_HITTER_WRC: f64 = 85.0;
pub const GOOD_HITTER_WRC: f64 = 115.0;

pub fn base_ceiling(profile: &FatigueProfile) -> f64 {
    let prior = match profile.role {
        PitcherRole::Starter => STARTER_PRIOR_PITCHES,
        PitcherRole::Reliever => RELIEVER_PRIOR_PITCHES,
    };
    let factor = (profile.season_appearances as f64 / FULL_SAMPLE_APPEARANCES).clamp(0.0, 1.0);
    let regressed_season = prior * (1.0 - factor) + profile.season_pitches_per_appearance * factor;
    let blend =
        (2.0 / 3.0) * regressed_season + (1.0 / 3.0) * profile.career_pitches_per_appearance;
    let mult = match profile.role {
        PitcherRole::Starter => STARTER_CEILING_MULT,
        PitcherRole::Reliever => RELIEVER_CEILING_MULT,
    };
    blend * mult
}

/// Inclusive window around the base ceiling, in pitches.
///
/// Age 30 and under is ±6 pitches. Age 38 and over is −14% to +4%.
/// Ages 31 through 37 sit on a straight line between those windows.
pub fn draw_window(age: u8, ceiling: f64) -> (f64, f64) {
    if age <= 30 {
        return (
            ceiling - YOUNG_DRAW_PITCHES as f64,
            ceiling + YOUNG_DRAW_PITCHES as f64,
        );
    }
    let old_down = ceiling * OLD_DOWNSIDE;
    let old_up = ceiling * OLD_UPSIDE;
    let t = ((age - 30) as f64 / 8.0).clamp(0.0, 1.0);
    let down = YOUNG_DRAW_PITCHES as f64 + t * (old_down - YOUNG_DRAW_PITCHES as f64);
    let up = YOUNG_DRAW_PITCHES as f64 + t * (old_up - YOUNG_DRAW_PITCHES as f64);
    (ceiling - down, ceiling + up)
}

pub fn draw_ceiling(profile: &FatigueProfile, rng: &mut impl Rng) -> f64 {
    let base = base_ceiling(profile);
    if profile.age <= 30 {
        let offset = rng.gen_range(-YOUNG_DRAW_PITCHES..=YOUNG_DRAW_PITCHES);
        return (base + f64::from(offset)).max(1.0);
    }
    let (low, high) = draw_window(profile.age, base);
    if high <= low {
        return low.max(1.0);
    }
    rng.gen_range(low..high).max(1.0)
}

/// Effort charged for one pitch. Low leverage against a weak hitter replaces the tier.
pub fn effort_per_pitch(leverage: f64, wrc_plus: f64) -> f64 {
    if leverage <= 0.7 && wrc_plus < WEAK_HITTER_WRC {
        return 0.90;
    }
    let mut cost = if leverage >= 2.0 {
        1.30
    } else if leverage >= 1.5 {
        1.15
    } else {
        1.0
    };
    if wrc_plus >= GOOD_HITTER_WRC {
        cost += 0.10;
    }
    cost
}

#[cfg(test)]
mod tests {
    use super::*;

    fn profile(role: PitcherRole, age: u8, season: f64, career: f64, apps: u32) -> FatigueProfile {
        FatigueProfile {
            role,
            age,
            season_pitches_per_appearance: season,
            career_pitches_per_appearance: career,
            season_appearances: apps,
        }
    }

    #[test]
    fn starter_blend_matches_the_102_to_120_example() {
        let ceiling = base_ceiling(&profile(PitcherRole::Starter, 28, 102.0, 102.0, 30));
        assert!((ceiling - 120.36).abs() < 1e-9);
    }

    #[test]
    fn thin_sample_regresses_toward_the_starter_prior() {
        let ceiling = base_ceiling(&profile(PitcherRole::Starter, 28, 60.0, 80.0, 0));
        // Season weight is zero, so the season rate is the 95 prior.
        // Blend = 2/3 * 95 + 1/3 * 80 = 90. Ceiling = 90 * 1.18 = 106.2.
        assert!((ceiling - 106.2).abs() < 1e-9);
    }

    #[test]
    fn half_sample_reliever_fades_the_season_weight() {
        let ceiling = base_ceiling(&profile(PitcherRole::Reliever, 27, 60.0, 90.0, 5));
        // factor 0.5, regressed = 0.5 * 18 + 0.5 * 60 = 39.
        // blend = 2/3 * 39 + 1/3 * 90 = 56. Ceiling = 61.6.
        assert!((ceiling - 61.6).abs() < 1e-9);
    }

    #[test]
    fn draw_windows_hit_the_stated_ends() {
        let (low, high) = draw_window(28, 120.0);
        assert!((low - 114.0).abs() < 1e-9);
        assert!((high - 126.0).abs() < 1e-9);

        let (low, high) = draw_window(38, 115.0);
        assert!((low - 98.9).abs() < 1e-9);
        assert!((high - 119.6).abs() < 1e-9);

        let (low, high) = draw_window(40, 115.0);
        assert!((low - 98.9).abs() < 1e-9);
        assert!((high - 119.6).abs() < 1e-9);
    }

    #[test]
    fn effort_table() {
        assert!((effort_per_pitch(1.0, 100.0) - 1.0).abs() < 1e-12);
        assert!((effort_per_pitch(1.5, 100.0) - 1.15).abs() < 1e-12);
        assert!((effort_per_pitch(2.0, 100.0) - 1.30).abs() < 1e-12);
        assert!((effort_per_pitch(1.0, 115.0) - 1.10).abs() < 1e-12);
        assert!((effort_per_pitch(2.0, 120.0) - 1.40).abs() < 1e-12);
        assert!((effort_per_pitch(0.7, 84.9) - 0.90).abs() < 1e-12);
        // 85 is not under the weak line, so the discount does not apply.
        assert!((effort_per_pitch(0.5, 85.0) - 1.0).abs() < 1e-12);
        assert!((effort_per_pitch(0.69, 70.0) - 0.90).abs() < 1e-12);
    }
}
