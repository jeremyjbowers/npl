//! Finished ratings, plate-appearance contracts, and the game objects they share.
//!
//! The sim reads the ratings it is given. It does not compute them.

use serde::{Deserialize, Serialize};

pub type PlayerId = String;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Position {
    #[serde(rename = "P")]
    Pitcher,
    #[serde(rename = "C")]
    Catcher,
    #[serde(rename = "1B")]
    First,
    #[serde(rename = "2B")]
    Second,
    #[serde(rename = "3B")]
    Third,
    #[serde(rename = "SS")]
    Shortstop,
    #[serde(rename = "LF")]
    Left,
    #[serde(rename = "CF")]
    Center,
    #[serde(rename = "RF")]
    Right,
    #[serde(rename = "DH")]
    Dh,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PitcherRole {
    Starter,
    Reliever,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Side {
    Away,
    Home,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Half {
    Top,
    Bottom,
}

impl Half {
    pub fn name(self) -> &'static str {
        match self {
            Self::Top => "Top",
            Self::Bottom => "Bottom",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    InProgress,
    Final,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Base {
    First,
    Second,
    Third,
}

/// Hitter outcomes per plate appearance. The eight rates sum to 1.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HitterRates {
    pub k: f64,
    pub bb: f64,
    pub hbp: f64,
    pub single: f64,
    pub double: f64,
    pub triple: f64,
    pub hr: f64,
    pub bip_out: f64,
}

impl HitterRates {
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

    /// Hits that are not home runs. The matchup splits this rate.
    pub fn non_hr_hits(&self) -> f64 {
        self.single + self.double + self.triple
    }

    pub fn hits(&self) -> f64 {
        self.non_hr_hits() + self.hr
    }
}

/// Pitcher outcomes per batter faced. `h` is hits that are not home runs.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PitcherRates {
    pub k: f64,
    pub bb: f64,
    pub hbp: f64,
    pub hr: f64,
    pub h: f64,
}

/// Shares of batted balls hit on the ground, in the air, and on a line. The three sum to 1.
/// A card that leaves them out is league average.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BattedBallRates {
    pub gb: f64,
    pub fb: f64,
    pub ld: f64,
}

impl Default for BattedBallRates {
    fn default() -> Self {
        Self {
            gb: crate::sim::LEAGUE_GB,
            fb: crate::sim::LEAGUE_FB,
            ld: crate::sim::LEAGUE_LD,
        }
    }
}

impl BattedBallRates {
    pub fn sum(&self) -> f64 {
        self.gb + self.fb + self.ld
    }
}

/// One higher-is-better number, and the position it was measured at.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DefenseRating {
    pub rating: f64,
    pub measured_at: Position,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Park {
    pub id: String,
    pub run_factor: f64,
}

/// Sample the fatigue line is drawn from. Not an outcome rating.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FatigueProfile {
    pub role: PitcherRole,
    pub age: u8,
    /// Pitches per appearance this season.
    pub season_pitches_per_appearance: f64,
    /// Career pitches per appearance.
    pub career_pitches_per_appearance: f64,
    pub season_appearances: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BatterCard {
    pub id: PlayerId,
    pub name: String,
    pub position: Position,
    pub defense: DefenseRating,
    pub wrc_plus: f64,
    pub rates: HitterRates,
    #[serde(default)]
    pub batted_balls: BattedBallRates,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PitcherCard {
    pub id: PlayerId,
    pub name: String,
    pub defense: DefenseRating,
    pub rates: PitcherRates,
    pub fatigue: FatigueProfile,
    #[serde(default)]
    pub batted_balls: BattedBallRates,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TeamFixture {
    pub id: String,
    pub name: String,
    pub home_park_id: String,
    pub lineup: Vec<BatterCard>,
    pub pitchers: Vec<PitcherCard>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GameFixture {
    pub postseason: bool,
    pub parks: Vec<Park>,
    /// Accepted and ignored. Weather has no effect until a weather file exists.
    pub weather: Option<String>,
    pub away: TeamFixture,
    pub home: TeamFixture,
}

/// The stub used by the distribution check. One hitter, one pitcher, one defense, one park.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DistributionFixture {
    pub id: PlayerId,
    pub wrc_plus: f64,
    pub rates: HitterRates,
    pub pitcher: PitcherRates,
    pub defense: DefenseRating,
    pub park: Park,
    pub weather: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct PrePaCalls {
    pub steal: bool,
    pub hit_and_run: bool,
    pub bunt: bool,
    pub intentional_walk: bool,
    /// Honored only with a runner on third and fewer than two outs.
    #[serde(default)]
    pub infield_in: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct Bases {
    pub first: Option<PlayerId>,
    pub second: Option<PlayerId>,
    pub third: Option<PlayerId>,
}

impl Bases {
    pub fn empty() -> Self {
        Self::default()
    }

    pub fn count(&self) -> u8 {
        u8::from(self.first.is_some())
            + u8::from(self.second.is_some())
            + u8::from(self.third.is_some())
    }

    pub fn any(&self) -> bool {
        self.count() > 0
    }
}

/// One runner's ratings from his card season. A missing number falls back to the league constant.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RunnerRating {
    pub id: PlayerId,
    /// Chance a steal succeeds, 0 to 1.
    #[serde(default)]
    pub steal_success: Option<f64>,
    /// FanGraphs Spd.
    #[serde(default)]
    pub spd: Option<f64>,
}

/// The ratings of the runners on base, carried beside `Bases`, which stores ids only.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct BaseRunners {
    #[serde(default)]
    pub first: Option<RunnerRating>,
    #[serde(default)]
    pub second: Option<RunnerRating>,
    #[serde(default)]
    pub third: Option<RunnerRating>,
}

impl BaseRunners {
    /// The rating carried for this runner, wherever it was given.
    pub fn for_runner(&self, id: &str) -> Option<&RunnerRating> {
        [&self.first, &self.second, &self.third]
            .into_iter()
            .flatten()
            .find(|rating| rating.id == id)
    }
}

/// Baserunning ratings for one plate appearance. Empty means every runner runs at the league constants.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct Running {
    #[serde(default)]
    pub runners: BaseRunners,
    /// Plate-appearance-weighted league Spd for the card season.
    #[serde(default)]
    pub league_spd: Option<f64>,
}

impl Running {
    /// Each rating must name the runner on its base and hold usable numbers.
    pub fn check(&self, bases: &Bases) -> Result<(), String> {
        let pairs = [
            ("first", &self.runners.first, &bases.first),
            ("second", &self.runners.second, &bases.second),
            ("third", &self.runners.third, &bases.third),
        ];
        for (base, rating, runner) in pairs {
            let Some(rating) = rating else { continue };
            if runner.as_deref() != Some(rating.id.as_str()) {
                return Err(format!(
                    "the rating on {base} is for {}, but {} is on {base}",
                    rating.id,
                    runner.as_deref().unwrap_or("nobody")
                ));
            }
            if let Some(rate) = rating.steal_success {
                if !(0.0..=1.0).contains(&rate) {
                    return Err(format!("steal_success for {} must be 0 to 1", rating.id));
                }
            }
            if let Some(spd) = rating.spd {
                if !spd.is_finite() || spd < 0.0 {
                    return Err(format!(
                        "spd for {} must be a number of at least 0",
                        rating.id
                    ));
                }
            }
        }
        if let Some(league) = self.league_spd {
            if !league.is_finite() || league <= 0.0 {
                return Err("league_spd must be a number above 0".to_string());
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Situation {
    pub inning: u8,
    pub half: Half,
    pub outs: u8,
    pub bases: Bases,
    pub away_score: u32,
    pub home_score: u32,
    /// Effort already spent by the pitcher on the mound. The sim receives it and does not spend it.
    pub pitcher_fatigue: f64,
    pub pitcher_ceiling: f64,
    pub postseason: bool,
}

/// What the state machine hands the sim. The sim stores none of it.
#[derive(Debug, Clone, PartialEq)]
pub struct PaInput {
    pub hitter_id: PlayerId,
    pub hitter_name: String,
    pub rates: HitterRates,
    /// On the input because the state machine already knows it. The sim does not draw with it.
    pub wrc_plus: f64,
    pub pitcher_id: PlayerId,
    pub pitcher_name: String,
    pub pitcher: PitcherRates,
    pub hitter_batted_balls: BattedBallRates,
    pub pitcher_batted_balls: BattedBallRates,
    /// One higher-is-better number for the defense on the field.
    pub defense: f64,
    pub situation: Situation,
    pub park: Park,
    pub weather: Option<String>,
    pub calls: PrePaCalls,
    /// Ratings of the runners in `situation.bases`, and the league speed they are measured against.
    pub running: Running,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PitchKind {
    Ball,
    CalledStrike,
    SwingingStrike,
    Foul,
    InPlay,
    HitByPitch,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Pitch {
    pub kind: PitchKind,
    /// Count after this pitch. Contact and hit-by-pitch do not add a ball or a strike.
    pub balls: u8,
    pub strikes: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct Count {
    pub balls: u8,
    pub strikes: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PlateOutcome {
    Strikeout,
    Walk,
    HitByPitch,
    IntentionalWalk,
    Single,
    Double,
    Triple,
    HomeRun,
    /// A ball-in-play out that holds every runner. The sim draws the three kinds below instead.
    BipOut,
    GroundOut,
    FlyOut,
    LineOut,
    GroundedIntoDoublePlay,
    SacrificeFly,
    BuntSacrifice,
    BuntSingle,
    BuntOut,
    CaughtStealing,
}

impl PlateOutcome {
    pub fn name(self) -> &'static str {
        match self {
            Self::Strikeout => "struck out",
            Self::Walk => "walked",
            Self::HitByPitch => "was hit by a pitch",
            Self::IntentionalWalk => "was intentionally walked",
            Self::Single => "singled",
            Self::Double => "doubled",
            Self::Triple => "tripled",
            Self::HomeRun => "homered",
            Self::BipOut => "was out on a ball in play",
            Self::GroundOut => "grounded out",
            Self::FlyOut => "flied out",
            Self::LineOut => "lined out",
            Self::GroundedIntoDoublePlay => "grounded into a double play",
            Self::SacrificeFly => "hit a sacrifice fly",
            Self::BuntSacrifice => "sacrificed",
            Self::BuntSingle => "bunted for a hit",
            Self::BuntOut => "bunted into an out",
            Self::CaughtStealing => "was caught stealing",
        }
    }

    pub fn is_hit(self) -> bool {
        matches!(
            self,
            Self::Single | Self::Double | Self::Triple | Self::HomeRun | Self::BuntSingle
        )
    }

    pub fn is_at_bat(self) -> bool {
        !matches!(
            self,
            Self::Walk
                | Self::HitByPitch
                | Self::IntentionalWalk
                | Self::BuntSacrifice
                | Self::SacrificeFly
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BaseOutRunChange {
    pub outs_added: u8,
    pub runs_scored: u8,
    pub bases: Bases,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum BaserunningEvent {
    Scored { runner: PlayerId },
    TookExtraBase { runner: PlayerId, to: Base },
    StolenBase { runner: PlayerId, to: Base },
    CaughtStealing { runner: PlayerId, at: Base },
}

/// Fielding resolved inside the plate appearance. Not a separate catch and throw.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Fielding {
    pub rating: f64,
    pub in_play: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PaResult {
    pub batter_id: PlayerId,
    pub pitcher_id: PlayerId,
    pub outcome: PlateOutcome,
    /// False when a baserunning out ended the plate appearance before the batter finished.
    pub batter_completed: bool,
    pub change: BaseOutRunChange,
    pub pitches: Vec<Pitch>,
    pub count: Count,
    pub baserunning: Vec<BaserunningEvent>,
    pub fielding: Fielding,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LogEntry {
    pub inning: u8,
    pub half: Half,
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct LineScore {
    pub away: Vec<u32>,
    pub home: Vec<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct Score {
    pub away: u32,
    pub home: u32,
}

/// Effort spent against the drawn pitch ceiling. Ordinary pitches cost 1, so the ceiling is in pitch units.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FatigueState {
    pub effort: f64,
    pub ceiling: f64,
    pub pitches: u32,
    pub outs_recorded: u32,
    pub runs_allowed: u32,
}

pub fn load_json<T: for<'de> Deserialize<'de>>(path: &str) -> Result<T, String> {
    let raw = std::fs::read_to_string(path).map_err(|err| format!("read {path}: {err}"))?;
    serde_json::from_str(&raw).map_err(|err| format!("parse {path}: {err}"))
}
