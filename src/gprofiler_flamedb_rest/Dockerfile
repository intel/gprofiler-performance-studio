FROM golang:1.24.0 AS build

ENV GO111MODULE on

WORKDIR /go

COPY . /go/src/

WORKDIR /go/src

RUN go get -v ./...
RUN go install -v ./...

RUN go build -v -o app


FROM debian:12.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl iputils-ping

RUN mkdir -p /data

COPY --from=build /go/src/app /usr/local/bin/app

RUN useradd -m -s /bin/bash -u 888 non_root && \
    chown -R non_root:non_root /data && \
    chown -R non_root:non_root /usr/local/bin/app

USER non_root


EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/app"]
