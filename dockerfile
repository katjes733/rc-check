FROM ubuntu:20.04

# Set environment variables to avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Update the package list and install dependencies
RUN apt-get update && \
    apt-get install -y software-properties-common curl cron vim && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.12 python3.12-distutils python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Set Python 3.12 as the default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# Install pip for Python 3.12
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python3.12 get-pip.py && \
    rm get-pip.py

# Verify the installation
RUN python3 --version && pip3 --version

ENV PATH="/usr/bin/python3:${PATH}"

RUN python3 -m pip install --upgrade pip

COPY ./requirements.txt .

RUN pip install -r requirements.txt

RUN playwright install --with-deps webkit

COPY cronjob /etc/cron.d/container_cronjob

RUN touch /var/log/cron.log
RUN crontab /etc/cron.d/container_cronjob

COPY ./main.py .
COPY ./.env .

CMD ["sh", "-c", "chmod 644 /etc/cron.d/container_cronjob && cron && tail -f /var/log/cron.log"]