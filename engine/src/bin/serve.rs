// ABOUTME: Runs the stateless engine HTTP service on 0.0.0.0 at $PORT (41731 when unset).
// ABOUTME: App Platform and the Django tests both start this binary.
//! Serve the stateless engine routes on 0.0.0.0. `PORT` picks the port; 41731 when unset.

use std::net::SocketAddr;
use std::process::ExitCode;

use baseball_engine::router;

const DEFAULT_PORT: u16 = 41731;

#[tokio::main]
async fn main() -> ExitCode {
    let port = match std::env::var("PORT") {
        Ok(raw) => match raw.parse::<u16>() {
            Ok(port) => port,
            Err(_) => {
                eprintln!("PORT must be a port number, not {raw:?}");
                return ExitCode::from(2);
            }
        },
        Err(_) => DEFAULT_PORT,
    };
    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    let listener = match tokio::net::TcpListener::bind(addr).await {
        Ok(listener) => listener,
        Err(err) => {
            eprintln!("bind {addr}: {err}");
            return ExitCode::from(1);
        }
    };
    println!("Engine listening on http://127.0.0.1:{port}");
    if let Err(err) = axum::serve(listener, router()).await {
        eprintln!("{err}");
        return ExitCode::from(1);
    }
    ExitCode::SUCCESS
}
