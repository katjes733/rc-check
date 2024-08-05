# Rivian Configuration Check

Rivian Configuration Check - Find your dream Rivian configuration faster and get notified automatically

## Description

This project aims to automate checking for the presence of specific configuration of Rivian vehicles in their shop. This can help you to quickly identify the availability of your dream configuration and make a quick move to purchase directly without needing to go through the lengthy process of getting a custom build.
Based on the URL, the containerized application runs on a schedule and retrieves the content of the website and analyzes it for the presence of the configuration specified by the URL.
If any new results are found, a message is sent to Slack channel to inform about those new results.

## Table of Contents

- [Rivian Configuration Check](#rivian-configuration-check)
  - [Description](#description)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
    - [Docker](#docker)
    - [Database](#database)
    - [Slack](#slack)
  - [Configure the application](#configure-the-application)
  - [Configure the check frequency](#configure-the-check-frequency)
  - [Build Docker Image for local use](#build-docker-image-for-local-use)
  - [Build Docker Image for QNAP Container Station](#build-docker-image-for-qnap-container-station)
  - [Pull Docker Image to QNAP Container Station](#pull-docker-image-to-qnap-container-station)
  - [Create Container](#create-container)

## Prerequisites

### Docker

To build Docker images for usage in QNAP Container Station, it is necessary to build the image as multi-platform. Therefore, the following prerequisite settings need to be enabled.

1. Turn on `Experimental Features` → `Access experimental features` in Docker Desktop.
2. First time run `docker buildx create --use`.

### Database

The application requires a PostgreSQL DB to be available where it stores data about the retrieved configurations.
The following steps should be performed to setup a container in QNAP Container Station.

1. Navigate to QNAP Container Station → `Images` and click on `Pull`. Set the following fields:
   - **Registry:** `Docker Hub`
   - **Image Name:** `postgres`
   - **Image Version:** `latest`
   - **Set to default:** *de-select*
2. Wait for the container to download.
3. Once `postgres` image is available, click on `+` (Create Container). Set the following fields and leave others with their respective defaults:
   - **Name:** *chose a reasonable name* (e.g. `postgres-1`)
   - **CPU Limit:** *set a reasonable limit* (e.g. `50%`)
   - **Memory Limit:** *set a reasonable limit* (e.g. `2048MB`)
   - **Advanced Settings:**
     - **Environment:** Create the following env vars:
       - **POSTGRES_DB**: *arbitrary DB name* (e.g. `postgres`)
       - **POSTGRES_USER**: *arbitrary DB user* (e.g. `postgres`)
       - **POSTGRES_PASSWORD**: *arbitrary DB password*
     - **Network:**
       - **Network Mode:** `Bridge`
       - **Use static IP**
         - Select a reasonable available static IP address.
     - **Shared Folders:**
       - **New Volume:** *select a reasonable name* (e.g. `postgres-1-db-volume`)
       - **Mount Point:** *leave default value*: `/var/lib/postgresql/data`
4. Wait for the Container to create. Then use an arbitrary PostgreSQL client (e.g. [pgAdmin](https://www.pgadmin.org/)) to test the connection to the DB.

### Slack

You should have a Slack workspace with a dedicated channel (can be private) for your RC-Check messages to be posted there.
To set up an incoming webhook for that channel perform the following steps:

1. In Slack, select your channel and open the channel details (right-click on channel → `View channel details`).
2. Select tab `Integrations` and click on `Add an app` in section `Apps`.
3. In `Add apps to <channel>` and search for `Incoming WebHooks`.
4. Click `Install` or `View` (if you already have added it to your workspace before). Then click `Configuration`, which opens the configuration for Incoming WebHooks in a browser window.
5. Click `Add to Slack`. Then select your `<channel>` and click on `Add Incoming WebHooks integration`.
6. Scroll to the bottom of the page and copy the Webhook URL (`<slack_url>`). Optionally customize the name and provide a description. Click `Save Settings`.

## Configure the application

1. Copy `env/.env.sample` to `.env` and populate it accordingly.
   1. PostgreSQL DB settings should be populated according to the settings in [Database](#database).
   2. Setup URLs to check and URL descriptions accordingly.
      1. Navigate to the [Rivian Shop](https://rivian.com/configurations) and configure your desired configuration using filters. Then copy the URL in the browser address bar. Use this URL as your URL to check.
   3. Use `<slack_url` for `SLACK_HOOK_URL`.
   4. It is recommended to leave `NOISY_MESSAGES` set to `false`. Otherwise a message will be posted every 5 minutes, regardless of any updates. With the setting `false`, only updates are posted.
   5. Adjust the `LOG_LEVEL` as necessary, but usually `info` is appropriate for most use cases.

## Configure the check frequency

By default, checks are run every 5 minutes. It is not recommended to go lower, but if a lower cadence is required, follow these steps:

1. Edit `cronjob`.
2. Replace only `*/5 * * * *` with a valid cron expression. You can create and test one [here](https://crontab.guru/).
3. Save changes.

## Build Docker Image for local use

This step is only relevant if you wish to run the container locally.

1. Run `docker buildx build --platform linux/amd64 -t rc-check --load .` to build `linux/amd64` version.

## Build Docker Image for QNAP Container Station

1. Run `docker login` and authenticate with your username and Personal Access Token (PAT) (see [Doker documentation](docs.docker.com/go/access-tokens)).
2. Build and push building for `x86` and `arm`: `docker buildx build --platform linux/amd64,linux/arm64 --push -t <registry>/rc-check:latest .` where `<registry>` is to be replaced with your desired destination registry (equivalent to your personal username).
   1. If you get stuck on `pushing layers` with a message such as `[auth] <registry>/rc-check:pull,push token for registry-1.docker.io` then do the following steps:
      1. Restart OS. Run `docker buildx ...` again to check if that helped.
      2. Make sure latest version of Docker Desktop is installed. Run `docker buildx ...` again to check if that helped.
      3. Make sure latest OS updates are installed. Run `docker buildx ...` again to check if that helped.
      4. Wait, even if it takes a while (up to 1h)

## Pull Docker Image to QNAP Container Station

1. Navigate to QNAP Container Station → `Images` and click on `Pull`. Set the following fields:
   - **Registry:** `Docker Hub`
   - **Image Name:** `<registry>/rc-check` (with `<registry>` being the registry where you pushed the image)
   - **Image Version:** `latest`
   - **Set to default:** *de-select*
2. Wait for the container to download.

## Create Container

1. Once `<registry>/rc-check` image is available in QNAP Container Station → `Images`, click on `+` (Create Container). Set the following fields and leave others with their respective defaults:
   - **Name:** *chose a reasonable name* (e.g. `rc-check-1`)
   - **CPU Limit:** *set a reasonable limit* (e.g. `20%`)
   - **Memory Limit:** *set a reasonable limit* (e.g. `1024MB`)
   - **Advanced Settings:**
     - **Network:**
       - **Network Mode:** `Bridge`
       - **Use static IP**
         - Select a reasonable available static IP address different from the `postgres` container IP address.
2. Wait for the Container to create.
3. Check the container log (wait at least for the configured cadence to see) to verify the applications runs correctly. If for some reason there was a configuration problem, you must go back to [Configure the application](#configure-the-application) and following steps. Alternatively you could overwrite/set environment variable values at the container level in QNAP Container Station directly, but this approach is recommended for testing only.
