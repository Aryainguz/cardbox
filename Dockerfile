# One image with the renderer (Python + Chromium + ffmpeg) and the Go API in front of it.
FROM golang:1.26-bookworm AS server
WORKDIR /src
COPY server/go.mod server/go.sum ./
RUN go mod download
COPY server/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /cardbox-server ./cmd/cardbox-server

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng libatomic1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && python -m playwright install --with-deps chromium
COPY --from=server /cardbox-server /usr/local/bin/cardbox-server
ENV CARDBOX_DATA=/data CARDBOX_ADDR=:8080
VOLUME /data
EXPOSE 8080
CMD ["cardbox-server"]
