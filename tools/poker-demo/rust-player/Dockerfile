FROM rust:1.90-bookworm AS build
WORKDIR /workspace

COPY sdks/rust /workspace/sdks/rust
COPY tools/poker-demo/rust-player /workspace/tools/poker-demo/rust-player

RUN cd /workspace/tools/poker-demo/rust-player && cargo build --release

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /workspace/tools/poker-demo/rust-player/target/release/poker-demo-rust-player /app/app

EXPOSE 8091
ENTRYPOINT ["/app/app"]
