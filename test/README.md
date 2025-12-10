# How to setup the test environment
This README aims to guide the user on how to run tests against **Gprofiler Performance Studio** services.

The executed tests can vary from:
* Unit;
* Integration;
* E2E (end-to-end);

The tested services can either:
* Run locally on the host machine, and **be managed** by the test environment;
* Run locally on the host machine, and **not be managed** by the test environment;
* Run remotely on a different machine;

By configuring the files on this folder, **the user should be capable to run tests for any combination of the above options for all services that compose the application**.

## Requirements
* Docker;
* Docker Compose;

If running services locally and managed by the test environment:
* You should be capable to run **Gprofiler Performance Studio** locally: [tutorial here](../README.md#usage);

## Configuring the test environment
This configuration determines:
* Which tests will be run;
* Which services will be run and managed by the test environment;
* Addresses, credentials and fine grain options for tests and services;

Overview of configuration files:
* [.env](./.env): This file configures all the **environment variables** that will be passed to the tests and services managed by the test environment. The user can modify this file to choose:

    * Addresses of services used by tests;
    * Credentials to be used to access services by tests;
    * Test options;
    * Service specific configuration (for services managed by the test environment);

* [docker-compose.yml](./docker-compose.yml): This file configures the containers that will be managed by the test environment. The user can modify this file to choose:

    * Tests to be run;
    * Ports to expose to host for each service managed by the test environment (should be rarely needed*);
    * Network options for the test container (to run the test container in "host" network mode in case there are local gprofiler services not managed by the test environment);


## Pre-deployment tests
**Description**: This test case aims to spin up local containers for all services and run tests against then.

**Use case**: Pre-deployment testing.

Start all containers, then attach to test container
```sh
docker compose --profile with-all up -d --build && docker attach gprofiler-tester
```
Stop all containers and remove persistent volumes
```sh
docker compose --profile with-all down -v
```

## Post deployment tests
**Description**: This test case aims to spin up only the test container and run tests against remote services.

**Use case**: Post-deployment testing.

Start all containers, then attach to test container
```sh
docker compose up -d --build && docker attach gprofiler-tester
```
Stop all containers and remove persistent volumes
```sh
docker compose down -v
```