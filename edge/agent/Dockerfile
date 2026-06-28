# Static, CGO-free build -> tiny runtime image. Cross-compile by setting
# TARGETARCH (docker buildx) e.g. linux/arm64 for a Jetson/RPi.
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
ARG TARGETARCH=amd64
RUN CGO_ENABLED=0 GOARCH=$TARGETARCH go build -o /out/siteiq-agent .

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/siteiq-agent /usr/local/bin/siteiq-agent
# Mount a volume at /data and set the env so config + outbox persist.
ENV SITEIQ_AGENT_CONFIG=/data/config.json \
    SITEIQ_AGENT_OUTBOX=/data/outbox.db
ENTRYPOINT ["/usr/local/bin/siteiq-agent"]
CMD ["run"]
