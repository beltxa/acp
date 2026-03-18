FROM golang:1.23 AS build
WORKDIR /workspace

COPY sdks/go /workspace/sdks/go
COPY tools/poker-demo/go-player /workspace/tools/poker-demo/go-player

RUN cd /workspace/tools/poker-demo/go-player && go build -o /workspace/tools/poker-demo/go-player/app .

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /workspace/tools/poker-demo/go-player/app /app/app

EXPOSE 8091
ENTRYPOINT ["/app/app"]
