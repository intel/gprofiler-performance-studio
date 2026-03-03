FROM golang:1.24.0 AS build

ENV GO111MODULE on

WORKDIR /go

COPY go.* src/
COPY *.go src/
COPY conf src/conf

WORKDIR /go/src

RUN go get -v ./...
RUN go install -v ./...
RUN go build -v

FROM debian:12.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates

RUN mkdir -p /data

COPY --from=build /go/src/main /indexer
COPY conf /conf

RUN useradd -m -s /bin/bash -u 888 non_root && \
    chown -R non_root:non_root /data && \
    chown -R non_root:non_root /indexer && \
    chown -R non_root:non_root /conf

USER non_root


ENTRYPOINT ["/indexer"]
