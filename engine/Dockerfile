# ABOUTME: Builds the stateless engine service (the `serve` binary) for its own App Platform component.
# ABOUTME: Listens on $PORT, 41731 by default; App Platform reaches it on an internal port only.
FROM rust:1.83-slim-bookworm AS build
WORKDIR /engine
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked --bin serve

FROM debian:bookworm-slim
COPY --from=build /engine/target/release/serve /usr/local/bin/engine
ENV PORT=41731
EXPOSE 41731
USER nobody
CMD ["engine"]
