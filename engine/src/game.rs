//! The game on the field.
//!
//! Illegal transitions are rejected. The sim does not own inning end, game end,
//! the three buckets, or the fatigue pull. Those happen here, between plate appearances.

use std::collections::BTreeMap;
use std::fmt;

use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use serde::{Deserialize, Serialize};

use crate::fatigue::{draw_ceiling, effort_per_pitch};
use crate::model::{
    Bases, BatterCard, DefenseRating, FatigueState, GameFixture, Half, LineScore, LogEntry,
    PaInput, PaResult, PitcherCard, PlayerId, Position, PrePaCalls, Running, Score, Side,
    Situation, Status, TeamFixture,
};

const FIELD_POSITIONS: [Position; 8] = [
    Position::Catcher,
    Position::First,
    Position::Second,
    Position::Third,
    Position::Shortstop,
    Position::Left,
    Position::Center,
    Position::Right,
];

#[derive(Debug, Clone, PartialEq)]
pub enum GameError {
    FourOuts { outs: u8, added: u8 },
    Reentry { player: PlayerId },
    LeftInPastFatigue { player: PlayerId },
    PitcherRequired,
    NoPitcherAvailable { team: Side },
    PitcherDoesNotHit { player: PlayerId },
    PositionRequired { player: PlayerId },
    GameOver,
    InvalidFixture(String),
    InvalidRunning(String),
    Store(String),
    TooLong,
}

impl fmt::Display for GameError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::FourOuts { outs, added } => {
                write!(f, "four outs rejected: {outs} outs with {added} more")
            }
            Self::Reentry { player } => write!(f, "{player} cannot re-enter"),
            Self::LeftInPastFatigue { player } => {
                write!(f, "{player} is past the fatigue line and cannot stay in")
            }
            Self::PitcherRequired => write!(f, "the mound is empty"),
            Self::NoPitcherAvailable { team } => {
                write!(f, "no pitcher available for {team:?}")
            }
            Self::PitcherDoesNotHit { player } => {
                write!(f, "{player} is a pitcher and cannot hit")
            }
            Self::PositionRequired { player } => {
                write!(
                    f,
                    "{player} needs a fielding position before the next pitch"
                )
            }
            Self::GameOver => write!(f, "the game is over"),
            Self::InvalidFixture(msg) => write!(f, "invalid fixture: {msg}"),
            Self::InvalidRunning(msg) => write!(f, "invalid runner ratings: {msg}"),
            Self::Store(msg) => write!(f, "store: {msg}"),
            Self::TooLong => write!(f, "the game did not end"),
        }
    }
}

impl std::error::Error for GameError {}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Club {
    pub id: String,
    pub name: String,
    pub home_park_id: String,
    pub lineup: Vec<BatterCard>,
    pub batter_index: usize,
    pub pitchers: Vec<PitcherCard>,
    pub pitcher_slot: Option<PlayerId>,
    /// Players in the game at a position.
    pub in_game: Vec<PlayerId>,
    /// Players available to enter.
    pub available: Vec<PlayerId>,
    /// Players already used. Re-entry is illegal.
    pub unavailable: Vec<PlayerId>,
    pub positions: BTreeMap<PlayerId, Position>,
    pub fatigue: BTreeMap<PlayerId, FatigueState>,
    /// Pinch hitters and pinch runners who have no fielding position yet. Each must be
    /// given one, or be replaced, before his club's next pitch in the field.
    #[serde(default)]
    pub pending: Vec<PlayerId>,
}

/// How a substitute enters a batting-order slot.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SubstituteRole {
    /// At the position of the player he replaces, who must not be on base.
    #[default]
    Replacement,
    /// For the batter due up. He holds the replaced player's position until he is given one.
    PinchHitter,
    /// For a runner on base, whose base he takes. He holds a position as a pinch hitter does.
    PinchRunner,
    /// While his club is in the field, at the position of the player he replaces.
    Defense,
}

/// One batting-order slot's new fielding position, with the defense rating his card has there.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PositionChange {
    pub index: usize,
    pub position: Position,
    pub defense: DefenseRating,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Game {
    pub postseason: bool,
    pub parks: Vec<crate::model::Park>,
    pub weather: Option<String>,
    pub away: Club,
    pub home: Club,
    pub inning: u8,
    pub half: Half,
    pub outs: u8,
    pub bases: Bases,
    pub score: Score,
    pub status: Status,
    pub log: Vec<LogEntry>,
    pub last_result: Option<PaResult>,
    pub results: Vec<PaResult>,
    pub line_score: LineScore,
}

impl Game {
    pub fn start(fixture: GameFixture, seed: u64) -> Result<Self, GameError> {
        let mut rng = StdRng::seed_from_u64(seed);
        Self::build(fixture, &mut rng)
    }

    pub fn start_random(fixture: GameFixture) -> Result<Self, GameError> {
        let mut rng = StdRng::from_entropy();
        Self::build(fixture, &mut rng)
    }

    fn build(fixture: GameFixture, rng: &mut impl Rng) -> Result<Self, GameError> {
        validate_fixture(&fixture)?;
        let away = seat_club(fixture.away, rng);
        let home = seat_club(fixture.home, rng);
        let mut game = Self {
            postseason: fixture.postseason,
            parks: fixture.parks,
            weather: fixture.weather,
            away,
            home,
            inning: 1,
            half: Half::Top,
            outs: 0,
            bases: Bases::empty(),
            score: Score::default(),
            status: Status::InProgress,
            log: Vec::new(),
            last_result: None,
            results: Vec::new(),
            line_score: LineScore::default(),
        };
        let away_starter = game.away.pitcher_slot.clone().unwrap_or_default();
        let home_starter = game.home.pitcher_slot.clone().unwrap_or_default();
        let away_name = game.pitcher_name(Side::Away, &away_starter);
        let home_name = game.pitcher_name(Side::Home, &home_starter);
        game.log.push(LogEntry {
            inning: 1,
            half: Half::Top,
            text: format!("{away_name} starts for {}.", game.away.name),
        });
        game.log.push(LogEntry {
            inning: 1,
            half: Half::Top,
            text: format!("{home_name} starts for {}.", game.home.name),
        });
        game.start_half();
        Ok(game)
    }

    pub fn fielding_side(&self) -> Side {
        match self.half {
            Half::Top => Side::Home,
            Half::Bottom => Side::Away,
        }
    }

    pub fn batting_side(&self) -> Side {
        match self.half {
            Half::Top => Side::Away,
            Half::Bottom => Side::Home,
        }
    }

    pub fn club(&self, side: Side) -> &Club {
        match side {
            Side::Away => &self.away,
            Side::Home => &self.home,
        }
    }

    pub fn club_mut(&mut self, side: Side) -> &mut Club {
        match side {
            Side::Away => &mut self.away,
            Side::Home => &mut self.home,
        }
    }

    pub fn current_pitcher(&self) -> Option<&PlayerId> {
        self.club(self.fielding_side()).pitcher_slot.as_ref()
    }

    pub fn is_final(&self) -> bool {
        self.status == Status::Final
    }

    /// Leverage used only for the effort table.
    ///
    /// inning 0.9 / 1.15 / 1.4, margin 1.3 / 1.15 / 0.95 / 0.75 / 0.55,
    /// outs 0.9 / 1.0 / 1.15, runners 1 + 0.15 each.
    pub fn leverage(&self) -> f64 {
        let inning_factor = if self.inning >= 9 {
            1.4
        } else if self.inning >= 7 {
            1.15
        } else {
            0.9
        };
        let margin = self.score.home.abs_diff(self.score.away);
        let margin_factor = match margin {
            0 => 1.3,
            1 => 1.15,
            2 => 0.95,
            3 => 0.75,
            _ => 0.55,
        };
        let out_factor = match self.outs {
            0 => 0.9,
            1 => 1.0,
            2 => 1.15,
            _ => 1.0,
        };
        let runner_factor = 1.0 + 0.15 * f64::from(self.bases.count());
        inning_factor * margin_factor * out_factor * runner_factor
    }

    pub fn plate_appearance_input(&self, calls: PrePaCalls) -> Result<PaInput, GameError> {
        self.begin_plate_appearance()?;
        let batting = self.batting_side();
        let fielding = self.fielding_side();
        let batter_index = self.club(batting).batter_index;
        let batter = self.club(batting).lineup[batter_index].clone();
        let pitcher_id = self
            .club(fielding)
            .pitcher_slot
            .clone()
            .ok_or(GameError::PitcherRequired)?;
        let pitcher = self
            .club(fielding)
            .pitchers
            .iter()
            .find(|card| card.id == pitcher_id)
            .cloned()
            .ok_or(GameError::PitcherRequired)?;
        let fatigue = self
            .club(fielding)
            .fatigue
            .get(&pitcher_id)
            .ok_or(GameError::PitcherRequired)?;
        Ok(PaInput {
            hitter_id: batter.id,
            hitter_name: batter.name,
            rates: batter.rates,
            wrc_plus: batter.wrc_plus,
            pitcher_id: pitcher.id.clone(),
            pitcher_name: pitcher.name,
            pitcher: pitcher.rates,
            hitter_batted_balls: batter.batted_balls,
            pitcher_batted_balls: pitcher.batted_balls,
            defense: self.defense_rating(fielding),
            situation: Situation {
                inning: self.inning,
                half: self.half,
                outs: self.outs,
                bases: self.bases.clone(),
                away_score: self.score.away,
                home_score: self.score.home,
                pitcher_fatigue: fatigue.effort,
                pitcher_ceiling: fatigue.ceiling,
                postseason: self.postseason,
            },
            park: self.home_park()?.clone(),
            weather: self.weather.clone(),
            calls,
            running: Running::default(),
        })
    }

    /// Sum of the eight fielders and the pitcher. The designated hitter does not field.
    pub fn defense_rating(&self, fielding: Side) -> f64 {
        let club = self.club(fielding);
        let mut total = 0.0;
        for batter in &club.lineup {
            if batter.position == Position::Dh {
                continue;
            }
            total += batter.defense.rating;
        }
        if let Some(pitcher_id) = &club.pitcher_slot {
            if let Some(pitcher) = club.pitchers.iter().find(|card| &card.id == pitcher_id) {
                total += pitcher.defense.rating;
            }
        }
        total
    }

    pub fn begin_plate_appearance(&self) -> Result<(), GameError> {
        if self.status == Status::Final {
            return Err(GameError::GameOver);
        }
        let fielding = self.fielding_side();
        let batting = self.batting_side();
        let pitcher_id = self
            .club(fielding)
            .pitcher_slot
            .clone()
            .ok_or(GameError::PitcherRequired)?;
        if self.pitcher_is_spent(fielding, &pitcher_id) {
            return Err(GameError::LeftInPastFatigue { player: pitcher_id });
        }
        if let Some(player) = self.club(fielding).pending.first() {
            return Err(GameError::PositionRequired {
                player: player.clone(),
            });
        }
        let batter = &self.club(batting).lineup[self.club(batting).batter_index];
        if self.is_pitcher(&batter.id) {
            return Err(GameError::PitcherDoesNotHit {
                player: batter.id.clone(),
            });
        }
        Ok(())
    }

    pub fn apply_plate_appearance(&mut self, result: PaResult) -> Result<(), GameError> {
        self.begin_plate_appearance()?;
        let total_outs = u16::from(self.outs) + u16::from(result.change.outs_added);
        if total_outs > 3 {
            return Err(GameError::FourOuts {
                outs: self.outs,
                added: result.change.outs_added,
            });
        }

        let batting = self.batting_side();
        let fielding = self.fielding_side();
        let batter = self.club(batting).lineup[self.club(batting).batter_index].clone();
        let pitcher_id = self.club(fielding).pitcher_slot.clone().unwrap();
        let cost = effort_per_pitch(self.leverage(), batter.wrc_plus);
        let pitches = result.pitches.len() as u32;
        let inning = self.inning;
        let half = self.half;

        self.outs += result.change.outs_added;
        self.bases = result.change.bases.clone();
        self.add_runs(result.change.runs_scored);
        if let Some(state) = self.club_mut(fielding).fatigue.get_mut(&pitcher_id) {
            state.effort += cost * f64::from(pitches);
            state.pitches += pitches;
            state.outs_recorded += u32::from(result.change.outs_added);
            state.runs_allowed += u32::from(result.change.runs_scored);
        }

        let count = format!("{}-{}", result.count.balls, result.count.strikes);
        self.log.push(LogEntry {
            inning,
            half,
            text: format!(
                "{} {}, {count}: {} {}. {} pitch{}.",
                half.name(),
                inning,
                batter.name,
                result.outcome.name(),
                pitches,
                if pitches == 1 { "" } else { "es" }
            ),
        });

        if result.batter_completed {
            let len = self.club(batting).lineup.len().max(1);
            let club = self.club_mut(batting);
            club.batter_index = (club.batter_index + 1) % len;
        }
        self.results.push(result.clone());
        self.last_result = Some(result);
        self.pull_if_spent(fielding);

        if self.walkoff() {
            self.status = Status::Final;
            let name = self.home.name.clone();
            self.log.push(LogEntry {
                inning: self.inning,
                half: self.half,
                text: format!("Walk-off. {name} wins."),
            });
            return Ok(());
        }
        if self.outs >= 3 {
            self.complete_half();
        }
        Ok(())
    }

    /// Put `player` on the mound for the fielding club. A spent or already used pitcher is rejected.
    pub(crate) fn seat_pitcher(
        &mut self,
        player: &str,
        rng: &mut impl Rng,
    ) -> Result<(), GameError> {
        let side = self.fielding_side();
        if !self
            .club(side)
            .pitchers
            .iter()
            .any(|card| card.id == player)
        {
            return Err(GameError::InvalidFixture(format!(
                "{player} is not a pitcher on the fielding club"
            )));
        }
        if self.club(side).unavailable.iter().any(|id| id == player) {
            return Err(GameError::Reentry {
                player: player.to_string(),
            });
        }
        if self.club(side).pitcher_slot.as_deref() == Some(player) {
            if self.pitcher_is_spent(side, player) {
                return Err(GameError::LeftInPastFatigue {
                    player: player.to_string(),
                });
            }
            return Ok(());
        }
        if !self.club(side).available.iter().any(|id| id == player) {
            return Err(GameError::InvalidFixture(format!(
                "{player} is not available"
            )));
        }

        if let Some(current) = self.club(side).pitcher_slot.clone() {
            self.move_to_unavailable(side, &current);
        }
        let profile = self
            .club(side)
            .pitchers
            .iter()
            .find(|card| card.id == player)
            .unwrap()
            .fatigue
            .clone();
        let ceiling = draw_ceiling(&profile, rng);
        let name = self.pitcher_name(side, player);
        let club = self.club_mut(side);
        club.available.retain(|id| id != player);
        if !club.in_game.iter().any(|id| id == player) {
            club.in_game.push(player.to_string());
        }
        club.positions.insert(player.to_string(), Position::Pitcher);
        club.pitcher_slot = Some(player.to_string());
        club.fatigue.insert(
            player.to_string(),
            FatigueState {
                effort: 0.0,
                ceiling,
                pitches: 0,
                outs_recorded: 0,
                runs_allowed: 0,
            },
        );
        self.log.push(LogEntry {
            inning: self.inning,
            half: self.half,
            text: format!("{name} enters to pitch."),
        });
        Ok(())
    }

    /// A pitching change for the fielding club, between plate appearances. A pitcher who is
    /// not on the staff yet joins it with this card; one already used cannot re-enter.
    /// The rng draws the new pitcher's fatigue line.
    pub fn bring_in_pitcher(
        &mut self,
        card: PitcherCard,
        rng: &mut impl Rng,
    ) -> Result<(), GameError> {
        if self.is_final() {
            return Err(GameError::GameOver);
        }
        check_pitcher_card(&card)?;
        let in_a_lineup = self
            .away
            .lineup
            .iter()
            .chain(&self.home.lineup)
            .any(|batter| batter.id == card.id);
        if in_a_lineup {
            return Err(GameError::InvalidFixture(format!(
                "{} is in a batting order and cannot pitch",
                card.id
            )));
        }
        let side = self.fielding_side();
        let other = match side {
            Side::Away => Side::Home,
            Side::Home => Side::Away,
        };
        if self.club(other).pitchers.iter().any(|p| p.id == card.id) {
            return Err(GameError::InvalidFixture(format!(
                "{} pitches for the other club",
                card.id
            )));
        }
        let id = card.id.clone();
        let club = self.club_mut(side);
        if !club.pitchers.iter().any(|p| p.id == id) {
            club.pitchers.push(card);
            club.available.push(id.clone());
        }
        self.seat_pitcher(&id, rng)
    }

    /// Put `card` in the batting-order slot `index` of `side`, at the same position.
    /// The player he replaces leaves the game and cannot re-enter.
    pub fn substitute_batter(
        &mut self,
        side: Side,
        index: usize,
        card: BatterCard,
    ) -> Result<(), GameError> {
        self.substitute(side, index, card, SubstituteRole::Replacement)
    }

    /// Put `card` in the batting-order slot `index` of `side`, at the position of the player he
    /// replaces, who leaves the game and cannot re-enter. `role` says when he may enter: a pinch
    /// hitter for the batter due up, a pinch runner for a runner on base (he takes the base), a
    /// defensive replacement while his club is in the field, or a plain replacement. A pinch
    /// hitter or runner for anyone but the designated hitter has no fielding position yet, and
    /// his club cannot pitch to a batter until he is given one or replaced.
    pub fn substitute(
        &mut self,
        side: Side,
        index: usize,
        card: BatterCard,
        role: SubstituteRole,
    ) -> Result<(), GameError> {
        if self.is_final() {
            return Err(GameError::GameOver);
        }
        if index >= self.club(side).lineup.len() {
            return Err(GameError::InvalidFixture(
                "batting-order index is out of range".into(),
            ));
        }
        if self.is_pitcher(&card.id) {
            return Err(GameError::PitcherDoesNotHit { player: card.id });
        }
        if self.club(side).unavailable.iter().any(|id| id == &card.id) {
            return Err(GameError::Reentry { player: card.id });
        }
        if self.club(side).in_game.iter().any(|id| id == &card.id) {
            return Err(GameError::InvalidFixture(format!(
                "{} is already in the game",
                card.id
            )));
        }
        check_hitter_rates(&card.rates, &card.id)?;
        check_batted_balls(&card.batted_balls, &card.id)?;
        let replaced = self.club(side).lineup[index].clone();
        if card.position != replaced.position {
            return Err(GameError::InvalidFixture(format!(
                "{} must play {:?}, the position of the player he replaces",
                card.id, replaced.position
            )));
        }
        let on_base = self.bases_holding(&replaced.id);
        match role {
            SubstituteRole::PinchHitter => {
                if side != self.batting_side() || index != self.club(side).batter_index {
                    return Err(GameError::InvalidFixture(format!(
                        "a pinch hitter replaces the batter due up, and {} is not due up",
                        replaced.id
                    )));
                }
            }
            SubstituteRole::PinchRunner => {
                if side != self.batting_side() || !on_base {
                    return Err(GameError::InvalidFixture(format!(
                        "a pinch runner replaces a runner on base, and {} is not on base",
                        replaced.id
                    )));
                }
            }
            SubstituteRole::Defense => {
                if side != self.fielding_side() {
                    return Err(GameError::InvalidFixture(
                        "a defensive replacement enters while his club is in the field".into(),
                    ));
                }
            }
            SubstituteRole::Replacement => {}
        }
        if on_base && role != SubstituteRole::PinchRunner {
            return Err(GameError::InvalidFixture(format!(
                "{} is on base and cannot be replaced at the plate",
                replaced.id
            )));
        }
        self.move_to_unavailable(side, &replaced.id);
        let text = match role {
            SubstituteRole::PinchHitter => format!(
                "{} pinch hits for {}, batting {}.",
                card.name,
                replaced.name,
                index + 1
            ),
            SubstituteRole::PinchRunner => {
                format!("{} pinch runs for {}.", card.name, replaced.name)
            }
            SubstituteRole::Replacement | SubstituteRole::Defense => format!(
                "{} replaces {}, batting {} and playing {:?}.",
                card.name,
                replaced.name,
                index + 1,
                card.position
            ),
        };
        for base in [
            &mut self.bases.first,
            &mut self.bases.second,
            &mut self.bases.third,
        ] {
            if base.as_deref() == Some(replaced.id.as_str()) {
                *base = Some(card.id.clone());
            }
        }
        let pinch = matches!(
            role,
            SubstituteRole::PinchHitter | SubstituteRole::PinchRunner
        );
        let club = self.club_mut(side);
        club.pending.retain(|id| id != &replaced.id);
        if pinch && card.position != Position::Dh {
            club.pending.push(card.id.clone());
        }
        club.in_game.push(card.id.clone());
        club.positions.insert(card.id.clone(), card.position);
        club.lineup[index] = card;
        self.log.push(LogEntry {
            inning: self.inning,
            half: self.half,
            text,
        });
        Ok(())
    }

    /// New fielding positions for some of the fielding club's batting-order slots, each with the
    /// defense rating his card has there. The designated hitter stays the designated hitter and
    /// nobody else becomes one. Afterward each of the eight field positions has one fielder.
    /// A pinch hitter or runner given a position no longer waits for one.
    pub fn set_positions(
        &mut self,
        side: Side,
        changes: Vec<PositionChange>,
    ) -> Result<(), GameError> {
        if self.is_final() {
            return Err(GameError::GameOver);
        }
        if side != self.fielding_side() {
            return Err(GameError::InvalidFixture(
                "positions change while the club is in the field".into(),
            ));
        }
        if changes.is_empty() {
            return Err(GameError::InvalidFixture("no position changes".into()));
        }
        let mut lineup = self.club(side).lineup.clone();
        let mut changed = Vec::new();
        for change in &changes {
            if change.index >= lineup.len() || changed.contains(&change.index) {
                return Err(GameError::InvalidFixture(
                    "each position change names a different batting-order slot".into(),
                ));
            }
            changed.push(change.index);
            let batter = &mut lineup[change.index];
            if batter.position == Position::Dh {
                return Err(GameError::InvalidFixture(format!(
                    "{} is the designated hitter and cannot move into the field",
                    batter.id
                )));
            }
            if !FIELD_POSITIONS.contains(&change.position) {
                return Err(GameError::InvalidFixture(format!(
                    "{} cannot move to {:?}; the designated hitter stays the designated hitter",
                    batter.id, change.position
                )));
            }
            if !change.defense.rating.is_finite() {
                return Err(GameError::InvalidFixture(format!(
                    "{} has a bad defense rating",
                    batter.id
                )));
            }
            batter.position = change.position;
            batter.defense = change.defense.clone();
        }
        for position in FIELD_POSITIONS {
            if lineup.iter().filter(|b| b.position == position).count() != 1 {
                return Err(GameError::InvalidFixture(format!(
                    "{position:?} must be played by exactly one fielder"
                )));
            }
        }
        let text = changes
            .iter()
            .map(|change| {
                let batter = &lineup[change.index];
                format!("{} plays {:?}.", batter.name, batter.position)
            })
            .collect::<Vec<_>>()
            .join(" ");
        let club = self.club_mut(side);
        for change in &changes {
            let id = lineup[change.index].id.clone();
            club.positions.insert(id.clone(), change.position);
            club.pending.retain(|pending| pending != &id);
        }
        club.lineup = lineup;
        self.log.push(LogEntry {
            inning: self.inning,
            half: self.half,
            text,
        });
        Ok(())
    }

    fn bases_holding(&self, player: &str) -> bool {
        [&self.bases.first, &self.bases.second, &self.bases.third]
            .into_iter()
            .any(|runner| runner.as_deref() == Some(player))
    }

    /// Fixed lineup. Pitchers are rejected before any other batting-order change.
    pub fn place_in_batting_order(
        &mut self,
        side: Side,
        index: usize,
        player: PlayerId,
    ) -> Result<(), GameError> {
        if self.is_pitcher(&player) {
            return Err(GameError::PitcherDoesNotHit { player });
        }
        if self.club(side).unavailable.iter().any(|id| id == &player) {
            return Err(GameError::Reentry { player });
        }
        if index >= self.club(side).lineup.len() {
            return Err(GameError::InvalidFixture(
                "batting-order index is out of range".into(),
            ));
        }
        let _ = index;
        Err(GameError::InvalidFixture(
            "the lineup is fixed for this game".into(),
        ))
    }

    pub(crate) fn pitcher_is_spent(&self, side: Side, player: &str) -> bool {
        self.club(side)
            .fatigue
            .get(player)
            .map(|state| state.effort >= state.ceiling)
            .unwrap_or(false)
    }

    fn is_pitcher(&self, player: &str) -> bool {
        self.away.pitchers.iter().any(|card| card.id == player)
            || self.home.pitchers.iter().any(|card| card.id == player)
    }

    fn pitcher_name(&self, side: Side, player: &str) -> String {
        self.club(side)
            .pitchers
            .iter()
            .find(|card| card.id == player)
            .map(|card| card.name.clone())
            .unwrap_or_else(|| player.to_string())
    }

    fn home_park(&self) -> Result<&crate::model::Park, GameError> {
        self.parks
            .iter()
            .find(|park| park.id == self.home.home_park_id)
            .ok_or_else(|| GameError::InvalidFixture("home park missing".into()))
    }

    fn add_runs(&mut self, runs: u8) {
        if runs == 0 {
            return;
        }
        let runs = u32::from(runs);
        let index = self.inning as usize - 1;
        match self.half {
            Half::Top => {
                self.score.away += runs;
                extend_line(&mut self.line_score.away, index);
                self.line_score.away[index] += runs;
            }
            Half::Bottom => {
                self.score.home += runs;
                extend_line(&mut self.line_score.home, index);
                self.line_score.home[index] += runs;
            }
        }
    }

    fn pull_if_spent(&mut self, side: Side) {
        let spent = self
            .club(side)
            .pitcher_slot
            .as_ref()
            .map(|id| self.pitcher_is_spent(side, id))
            .unwrap_or(false);
        if !spent {
            return;
        }
        let pitcher_id = self.club(side).pitcher_slot.clone().unwrap();
        let name = self.pitcher_name(side, &pitcher_id);
        self.move_to_unavailable(side, &pitcher_id);
        self.log.push(LogEntry {
            inning: self.inning,
            half: self.half,
            text: format!("{name} is pulled. The mound is empty."),
        });
    }

    fn move_to_unavailable(&mut self, side: Side, player: &str) {
        let club = self.club_mut(side);
        club.in_game.retain(|id| id != player);
        club.available.retain(|id| id != player);
        if !club.unavailable.iter().any(|id| id == player) {
            club.unavailable.push(player.to_string());
        }
        club.positions.remove(player);
        if club.pitcher_slot.as_deref() == Some(player) {
            club.pitcher_slot = None;
        }
    }

    fn walkoff(&self) -> bool {
        self.half == Half::Bottom && self.inning >= 9 && self.score.home > self.score.away
    }

    fn complete_half(&mut self) {
        self.outs = 0;
        self.bases = Bases::empty();
        match self.half {
            Half::Top => {
                if self.inning >= 9 && self.score.home > self.score.away {
                    self.status = Status::Final;
                    self.log.push(LogEntry {
                        inning: self.inning,
                        half: Half::Top,
                        text: "Home leads after the top of the inning. Game over.".into(),
                    });
                    return;
                }
                self.half = Half::Bottom;
                self.start_half();
            }
            Half::Bottom => {
                if self.inning >= 9 && self.score.home != self.score.away {
                    self.status = Status::Final;
                    self.log.push(LogEntry {
                        inning: self.inning,
                        half: Half::Bottom,
                        text: "Final.".into(),
                    });
                    return;
                }
                self.inning += 1;
                self.half = Half::Top;
                self.start_half();
            }
        }
    }

    fn start_half(&mut self) {
        self.bases = Bases::empty();
        self.outs = 0;
        let index = self.inning as usize - 1;
        match self.half {
            Half::Top => extend_line(&mut self.line_score.away, index),
            Half::Bottom => extend_line(&mut self.line_score.home, index),
        }
        if !self.postseason && self.inning >= 10 {
            self.place_ghost_runner();
        }
    }

    fn place_ghost_runner(&mut self) {
        let side = self.batting_side();
        let len = self.club(side).lineup.len();
        if len == 0 {
            return;
        }
        let leadoff = self.club(side).batter_index % len;
        let ghost_index = (leadoff + len - 1) % len;
        let ghost = self.club(side).lineup[ghost_index].id.clone();
        let name = self.club(side).lineup[ghost_index].name.clone();
        self.bases.second = Some(ghost);
        self.log.push(LogEntry {
            inning: self.inning,
            half: self.half,
            text: format!("Extra innings. {name} starts on second."),
        });
    }
}

fn extend_line(line: &mut Vec<u32>, index: usize) {
    while line.len() <= index {
        line.push(0);
    }
}

fn seat_club(team: TeamFixture, rng: &mut impl Rng) -> Club {
    let mut in_game = Vec::new();
    let mut positions = BTreeMap::new();
    for batter in &team.lineup {
        in_game.push(batter.id.clone());
        positions.insert(batter.id.clone(), batter.position);
    }
    let mut available = Vec::new();
    let mut fatigue = BTreeMap::new();
    let mut pitcher_slot = None;
    for (index, pitcher) in team.pitchers.iter().enumerate() {
        if index == 0 {
            in_game.push(pitcher.id.clone());
            positions.insert(pitcher.id.clone(), Position::Pitcher);
            pitcher_slot = Some(pitcher.id.clone());
            fatigue.insert(
                pitcher.id.clone(),
                FatigueState {
                    effort: 0.0,
                    ceiling: draw_ceiling(&pitcher.fatigue, rng),
                    pitches: 0,
                    outs_recorded: 0,
                    runs_allowed: 0,
                },
            );
        } else {
            available.push(pitcher.id.clone());
        }
    }
    Club {
        id: team.id,
        name: team.name,
        home_park_id: team.home_park_id,
        lineup: team.lineup,
        batter_index: 0,
        pitchers: team.pitchers,
        pitcher_slot,
        in_game,
        available,
        unavailable: Vec::new(),
        positions,
        fatigue,
        pending: Vec::new(),
    }
}

fn validate_fixture(fixture: &GameFixture) -> Result<(), GameError> {
    if fixture.parks.is_empty() {
        return Err(GameError::InvalidFixture("no parks".into()));
    }
    for park in &fixture.parks {
        if !park.run_factor.is_finite() || park.run_factor <= 0.0 {
            return Err(GameError::InvalidFixture(format!(
                "park {} has run factor {}",
                park.id, park.run_factor
            )));
        }
    }
    validate_team(&fixture.away, fixture)?;
    validate_team(&fixture.home, fixture)?;
    let mut ids = Vec::new();
    for batter in fixture.away.lineup.iter().chain(&fixture.home.lineup) {
        ids.push(batter.id.clone());
    }
    for pitcher in fixture.away.pitchers.iter().chain(&fixture.home.pitchers) {
        ids.push(pitcher.id.clone());
    }
    ids.sort();
    for pair in ids.windows(2) {
        if pair[0] == pair[1] {
            return Err(GameError::InvalidFixture(format!(
                "duplicate player id {}",
                pair[0]
            )));
        }
    }
    Ok(())
}

fn validate_team(team: &TeamFixture, fixture: &GameFixture) -> Result<(), GameError> {
    if !fixture
        .parks
        .iter()
        .any(|park| park.id == team.home_park_id)
    {
        return Err(GameError::InvalidFixture(format!(
            "{} has no home park {}",
            team.name, team.home_park_id
        )));
    }
    if team.lineup.len() != 9 {
        return Err(GameError::InvalidFixture(format!(
            "{} needs 9 batters",
            team.name
        )));
    }
    if team.pitchers.is_empty() {
        return Err(GameError::InvalidFixture(format!(
            "{} needs a pitcher",
            team.name
        )));
    }
    let mut seen = [false; 8];
    let mut dh = 0;
    for batter in &team.lineup {
        if team.pitchers.iter().any(|pitcher| pitcher.id == batter.id) {
            return Err(GameError::InvalidFixture(format!(
                "pitcher {} is in the batting order",
                batter.id
            )));
        }
        check_hitter_rates(&batter.rates, &batter.id)?;
        check_batted_balls(&batter.batted_balls, &batter.id)?;
        if batter.position == Position::Dh {
            dh += 1;
            continue;
        }
        if batter.position == Position::Pitcher {
            return Err(GameError::InvalidFixture(format!(
                "{} is batting",
                batter.id
            )));
        }
        match FIELD_POSITIONS
            .iter()
            .position(|pos| *pos == batter.position)
        {
            Some(index) if !seen[index] => seen[index] = true,
            Some(_) => {
                return Err(GameError::InvalidFixture(format!(
                    "{} repeats a position",
                    team.name
                )))
            }
            None => {
                return Err(GameError::InvalidFixture(format!(
                    "{} has an uncovered position",
                    batter.id
                )))
            }
        }
    }
    if dh != 1 || seen.iter().any(|slot| !slot) {
        return Err(GameError::InvalidFixture(format!(
            "{} must field eight defenders and a designated hitter",
            team.name
        )));
    }
    for pitcher in &team.pitchers {
        check_pitcher_card(pitcher)?;
    }
    Ok(())
}

fn check_pitcher_card(pitcher: &PitcherCard) -> Result<(), GameError> {
    for (name, rate) in [
        ("k", pitcher.rates.k),
        ("bb", pitcher.rates.bb),
        ("hbp", pitcher.rates.hbp),
        ("hr", pitcher.rates.hr),
        ("h", pitcher.rates.h),
    ] {
        if !(0.0..1.0).contains(&rate) {
            return Err(GameError::InvalidFixture(format!(
                "{} {name} is out of range",
                pitcher.id
            )));
        }
    }
    check_batted_balls(&pitcher.batted_balls, &pitcher.id)?;
    if pitcher.fatigue.season_pitches_per_appearance <= 0.0
        || pitcher.fatigue.career_pitches_per_appearance <= 0.0
        || pitcher.fatigue.age == 0
    {
        return Err(GameError::InvalidFixture(format!(
            "{} has a bad fatigue profile",
            pitcher.id
        )));
    }
    Ok(())
}

fn check_hitter_rates(rates: &crate::model::HitterRates, id: &str) -> Result<(), GameError> {
    for (name, rate) in [
        ("k", rates.k),
        ("bb", rates.bb),
        ("hbp", rates.hbp),
        ("single", rates.single),
        ("double", rates.double),
        ("triple", rates.triple),
        ("hr", rates.hr),
        ("bip_out", rates.bip_out),
    ] {
        if !(0.0..=1.0).contains(&rate) {
            return Err(GameError::InvalidFixture(format!(
                "{id} {name} is out of range"
            )));
        }
    }
    let sum = rates.sum();
    if (sum - 1.0).abs() > 1e-6 {
        return Err(GameError::InvalidFixture(format!(
            "{id} rates sum to {sum}"
        )));
    }
    Ok(())
}

fn check_batted_balls(rates: &crate::model::BattedBallRates, id: &str) -> Result<(), GameError> {
    for (name, rate) in [("gb", rates.gb), ("fb", rates.fb), ("ld", rates.ld)] {
        if !(0.0..=1.0).contains(&rate) {
            return Err(GameError::InvalidFixture(format!(
                "{id} batted-ball {name} is out of range"
            )));
        }
    }
    let sum = rates.sum();
    if (sum - 1.0).abs() > 1e-6 {
        return Err(GameError::InvalidFixture(format!(
            "{id} batted-ball rates sum to {sum}"
        )));
    }
    Ok(())
}
