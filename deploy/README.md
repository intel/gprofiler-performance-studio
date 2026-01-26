# Info
This guide aims to help users setup a local development environment for **Gprofiler Performance Studio**.

The end goal being:
* Have all services running locally as containers;
* Have the ability to orchestrate dev containers using **Docker Compose**;
* Have the ability to correctly expose and forward service ports to local development tools (in case the test environment needs to be run on remote host machine);

Some steps present here are already part of the [general guides of the project](../README.md#usage).

## 1. Pre-requisites
Before using the Continuous Profiler, ensure the following:
- You have an AWS account and configure your credentials, as the project utilizes AWS SQS and S3.
- You'll also need to create an SQS queue and an S3 bucket.
- You have Docker and docker-compose installed on your machine.


### 1.1 Security
By default, the system is required to set a basic auth username and password;
you can generate it by running the following command:
```shell
# assuming that you located in the deploy directory
htpasswd -B -C 12 -c .htpasswd <your username>
# the prompt will ask you to set a password
```
This file is required to run the stack

Also, a TLS certificate is required to run the stack,
see [Securing Connections with SSL/TLS](#securing-connections-with-ssltls) for more details.

### 1.2 Securing Connections with SSL/TLS
When accessing the Continuous Profiler UI through the web,
it is important to set up HTTPS to ensure the communication between Continuous Profiler and the end user is encrypted.
As well as communication between webapp and ch-rest-service expected to be encrypted.

Besides the security aspect, this is also required
for the browser to allow the use of some UI features that are blocked by browsers for non-HTTPS connections.


The TLS is enabled by default, but it requires you to provide a certificates:

Main nginx certificates location
- `deploy/tls/cert.pem` - TLS certificate
- `deploy/tls/key.pem` - TLS key

CH REST service certificates location:
- `deploy/tls/ch_rest_cert.pem` - TLS certificate
- `deploy/tls/ch_rest_key.pem` - TLS key

_See [Self-signed certificate](#self-signed-certificate) for more details._

#### 1.2.1 Self-signed certificate
If you don't have a certificate, you can generate a self-signed certificate using the following command:
```shell
cd deploy
mkdir -p tls
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout tls/key.pem -out tls/cert.pem
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout tls/ch_rest_key.pem -out tls/ch_rest_cert.pem
```
Pay attention, self-signed certificates are not trusted by browsers and will require you to add an exception.

:bangbang: IMPORTANT: If you are using a self-signed certificate,
you need the agent to trust it,
or to disable the TLS verification by adding `--no-verify` flag to the agent configuration.

For example,
that will run a docker installation agent with self-signed certificate
(that will communicate from docker network to host network):
```shell
docker run --name granulate-gprofiler --restart=always -d --pid=host --userns=host --privileged intel/gprofiler:latest -cu --token="<token from api or ui>" --service-name="my-super-service" --server-host "https://host.docker.internal" --glogger-server "https://host.docker.internal" --no-verify
```

### 1.3 Port exposure for local development tools
Make sure to uncomment the "ports" definition for each service you want to expose on [docker-compose.yml](./docker-compose.yml).

Also, make sure to correctly configure the port on your host machine that you want to bind to the port on the container. Ex:
```Dockerfile
#...
    ports:
        - "<your-host-machine-port>:<container-port>"
#...
```

### 1.4 [Optional] Port forwarding via SSH for remote dev environment
**This step should only be completed in case your dev environment is running on a remote machine, but your dev tools (i.e postman, db client, browser) are running on you local machine.**

Also, this technique is particularly useful for cases where you don't want to (or can't) open ports on your remote machine for debugging.

#### 1.4.1 [Optional] Configure SSH client to forward specific ports for specific host
1- Open the configuration file for your SSH client:
```sh
vim ~/.ssh/config
```
2- Modify or include port forwarding options tho the remote host
```configfile
Host <remote-host-alias-for-ssh-client>
  User <remote-host-user>
  ForwardAgent yes
  HostName <remote-host-address>
  # This port forwarding config intends to forward the 443 port used by the load balancer service to the local host
  LocalForward 443 127.0.0.1:443
  # This port forwarding config intends to forward the 5432 port used by the postgres service to the local host
  LocalForward 5432 127.0.0.1:5432
```
3- Reconnect to the remote host with the new config
```sh
ssh <remote-host-alias-for-ssh-client>
```

### 1.5 Environment Configuration
Before running the stack, you need to configure the environment variables in the `.env` file located in the `deploy` directory. This file contains all the necessary configuration for the services to communicate with each other and external dependencies.

#### 1.5.1 Required AWS Configuration
```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-aws-access-key>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-key>
AWS_SESSION_TOKEN=<your-session-token>  # Optional, only if using temporary credentials

# S3 and SQS resources
BUCKET_NAME=<your-s3-bucket-name>
SQS_INDEXER_QUEUE_URL=<your-sqs-queue-url>
```

#### 1.5.2 Database Configuration
```bash
# PostgreSQL (main application database)
POSTGRES_USER=<postgres-username>
POSTGRES_PASSWORD=<postgres-password>
POSTGRES_DB=<postgres-database-name>
POSTGRES_PORT=5432
POSTGRES_HOST=db_postgres  # Docker service name for local development

# ClickHouse (analytics database)
CLICKHOUSE_USER=<clickhouse-username>
CLICKHOUSE_PASSWORD=<clickhouse-password>
CLICKHOUSE_HOST=db_clickhouse  # Docker service name for local development
```

#### 1.5.3 Service Authentication
```bash
# REST API service credentials
REST_USERNAME=<rest-api-username>
REST_PASSWORD=<rest-api-password>

# Domain configuration
DOMAIN=http://localhost  # Used in agent installation templates
```

#### 1.5.4 Slack Integration (New)
The gProfiler service now supports Slack notifications for profiling activities:

```bash
# Slack Bot Token - obtain from your Slack app configuration
SLACK_BOT_TOKEN=<your-slack-bot-token>

# Slack Channels - comma-separated list of channels for notifications
SLACK_CHANNELS="<#channel1>,<#channel2>"
```

**Setting up Slack Integration:**
1. Create a Slack App in your workspace or use an existing one
2. Add the following OAuth scopes to your bot: `chat:write`, `channels:read`, `groups:read`
3. Install the app to your workspace and copy the Bot User OAuth Token
4. Set the `SLACK_BOT_TOKEN` with your token (starts with `xoxb-`)
5. Configure `SLACK_CHANNELS` with the channels where you want notifications (use comma-separated format)

#### 1.5.5 Logging Configuration
```bash
# Common logging directory for all services
COMMON_LOGS_DIR=/logs

# Service-specific log file paths
WEBAPP_APP_LOG_FILE_PATH="webapp.log"
AGENTS_LOGS_APP_LOG_FILE_PATH="${COMMON_LOGS_DIR}/agents-logs-app.log"
AGENTS_LOGS_LOG_FILE_PATH="${COMMON_LOGS_DIR}/agents-logs.log"
```

**Note:** The `.env` file comes with sensible defaults for local development. You primarily need to:
1. Configure your AWS credentials and resources
2. Set up Slack integration (if desired)
3. Adjust database passwords for production environments

## 2. Running the stack
To run the entire stack built from source, use the docker-compose project located in the `deploy` directory.

The `deploy` directory contains:
- `docker-compose.yml` - The Docker compose file.
- `.env` - The environment file where you set your AWS credentials, SQS/S3 names, and AWS region.
- `https_nginx.conf` - Nginx configuration file used as an entrypoint load balancer.
- `diagnostics.sh`- A script for testing connectivity between services and printing useful information.
- `tls` - A directory for storing TLS certificates (see [Securing Connections with SSL/TLS](#securing-connections-with-ssltls)).
- `.htpasswd` - A file for storing basic auth credentials (see above).

To launch the stack, run the following commands in the `deploy` directory:
```shell
cd deploy
docker-compose --profile with-clickhouse up -d --build
```

Check that all services are running:
```shell
docker-compose ps
```

You should see the following containers with the prefix 'gprofiler-ps*':
* gprofiler-ps-agents-logs-backend
* gprofiler-ps-ch-indexer
* gprofiler-ps-ch-rest-service
* gprofiler-ps-clickhouse
* gprofiler-ps-nginx-load-balancer
* gprofiler-ps-periodic-tasks
* gprofiler-ps-postgres
* gprofiler-ps-webapp

Now You can access the UI by navigating to https://localhost:4433 in your browser
(4433 is the default port, configurable in the docker-compose.yml file).

## 3. Destroying the stack
```shell
docker-compose --profile with-clickhouse down -v
```
The `-v` option deletes also the volumes that mens that all data will be truncated
