//! Play one regular-season game from `fixtures/game.json`.

use std::env;
use std::process::ExitCode;

use baseball_engine::{
    play_game, ComputerManager, Game, GameFixture, Governance, PlateOutcome, Sim,
};

fn main() -> ExitCode {
    let path = env::args()
        .nth(1)
        .unwrap_or_else(|| concat!(env!("CARGO_MANIFEST_DIR"), "/fixtures/game.json").to_string());
    let fixture = match load(&path) {
        Ok(fixture) => fixture,
        Err(err) => {
            eprintln!("{err}");
            return ExitCode::from(1);
        }
    };
    let mut game = match Game::start_random(fixture) {
        Ok(game) => game,
        Err(err) => {
            eprintln!("{err}");
            return ExitCode::from(1);
        }
    };
    let mut sim = Sim::from_entropy();
    let mut manager = ComputerManager::from_entropy();
    let governance = Governance::new();
    if let Err(err) = play_game(&mut game, &mut sim, &mut manager, &governance) {
        eprintln!("{err}");
        return ExitCode::from(1);
    }
    print_game(&game);
    ExitCode::SUCCESS
}

fn load(path: &str) -> Result<GameFixture, String> {
    baseball_engine::load_json(path)
}

fn print_game(game: &Game) {
    let park = game
        .parks
        .iter()
        .find(|park| park.id == game.home.home_park_id);
    let park_line = match park {
        Some(park) => format!("{} (run factor {:.1})", park.id, park.run_factor),
        None => "unknown park".to_string(),
    };
    let season = if game.postseason {
        "Postseason"
    } else {
        "Regular season"
    };
    println!("{season} at {park_line}");
    println!(
        "{} {}, {} {}",
        game.away.name, game.score.away, game.home.name, game.score.home
    );
    println!();
    let width = game.line_score.away.len().max(game.line_score.home.len());
    let mut header = String::from("   ");
    for inning in 1..=width {
        header.push_str(&format!("{inning:>2} "));
    }
    header.push_str(" R");
    println!("{header}");
    println!(
        "A  {} {:>2}",
        cells(&game.line_score.away, width),
        game.score.away
    );
    println!(
        "H  {} {:>2}",
        cells(&game.line_score.home, width),
        game.score.home
    );
    println!();
    print_batting("Visitors", game, baseball_engine::Side::Away);
    println!();
    print_batting("Home", game, baseball_engine::Side::Home);
    println!();
    print_pitching("Visitors", game, baseball_engine::Side::Away);
    print_pitching("Home", game, baseball_engine::Side::Home);
    println!();
    println!("Play by play");
    for entry in &game.log {
        println!("{}", entry.text);
    }
}

fn cells(line: &[u32], width: usize) -> String {
    let mut parts = Vec::new();
    for index in 0..width {
        if index >= line.len() {
            parts.push("  ".to_string());
        } else {
            parts.push(format!("{:>2}", line[index]));
        }
    }
    parts.join(" ")
}

fn print_batting(title: &str, game: &Game, side: baseball_engine::Side) {
    println!("{title} batting");
    println!(
        "{:<18} {:>3} {:>3} {:>3} {:>3} {:>3} {:>3}",
        "Batter", "AB", "H", "HR", "BB", "K", "RBI"
    );
    let club = game.club(side);
    for batter in &club.lineup {
        let mut ab = 0;
        let mut hits = 0;
        let mut hr = 0;
        let mut bb = 0;
        let mut k = 0;
        let mut rbi = 0;
        for result in &game.results {
            if result.batter_id != batter.id || !result.batter_completed {
                continue;
            }
            if result.outcome.is_at_bat() {
                ab += 1;
            }
            if result.outcome.is_hit() {
                hits += 1;
            }
            if result.outcome == PlateOutcome::HomeRun {
                hr += 1;
            }
            if matches!(
                result.outcome,
                PlateOutcome::Walk | PlateOutcome::IntentionalWalk
            ) {
                bb += 1;
            }
            if result.outcome == PlateOutcome::Strikeout {
                k += 1;
            }
            rbi += result.change.runs_scored;
        }
        println!(
            "{:<18} {ab:>3} {hits:>3} {hr:>3} {bb:>3} {k:>3} {rbi:>3}",
            batter.name
        );
    }
}

fn print_pitching(title: &str, game: &Game, side: baseball_engine::Side) {
    println!("{title} pitching");
    let club = game.club(side);
    for pitcher in &club.pitchers {
        let Some(state) = club.fatigue.get(&pitcher.id) else {
            continue;
        };
        if state.pitches == 0 && club.pitcher_slot.as_deref() != Some(pitcher.id.as_str()) {
            continue;
        }
        let whole = state.outs_recorded / 3;
        let frac = state.outs_recorded % 3;
        println!(
            "  {}  {whole}.{frac} IP, {} pitches, {:.1} effort, line {:.1}, {} runs",
            pitcher.name, state.pitches, state.effort, state.ceiling, state.runs_allowed
        );
    }
}
