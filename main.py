"""
RC Check
"""
import logging
from logging.handlers import TimedRotatingFileHandler
import time
from datetime import datetime
import os
import re
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

from playwright.sync_api import sync_playwright

import psycopg2
from peewee import Model, TextField
from playhouse.postgres_ext import BinaryJSONField, DateTimeTZField, PostgresqlExtDatabase


CONST_ENCODING = 'utf-8'

load_dotenv()

levels = {
    'critical': logging.CRITICAL,
    'error': logging.ERROR,
    'warn': logging.WARNING,
    'info': logging.INFO,
    'debug': logging.DEBUG
}
logger = logging.getLogger()
formatter = logging.Formatter('%(asctime)s - %(thread)d - %(levelname)s - %(message)s')
if os.getenv('LOG_FILE'):
    file_output_handler = \
        TimedRotatingFileHandler(
            os.getenv('LOG_FILE'),
            when="midnight",
            encoding=CONST_ENCODING
        )
    file_output_handler.setFormatter(formatter)
    logger.addHandler(file_output_handler)
console_output_handler = logging.StreamHandler()
console_output_handler.setFormatter(formatter)
logger.addHandler(console_output_handler)
try:
    logger.setLevel(levels.get(os.getenv('LOG_LEVEL', 'info').lower()))
except KeyError:
    logger.setLevel(logging.INFO)

db = PostgresqlExtDatabase(
    os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASS'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT')
)


class RcCheckModel(Model):
    """
    Entity for RC Check.

    Args:
        Model (Model): The Model
    """
    url = TextField(primary_key=True, null=False)
    url_description = TextField(null=True)
    created_time = DateTimeTZField(default=datetime.now)
    modified_time = DateTimeTZField(default=datetime.now)
    last_checked_time = DateTimeTZField(default=datetime.now)
    configurations = BinaryJSONField(default=[])

    class Meta:
        """
        Meta data
        """
        database = db
        table_name = 'rc_check'


logger.debug(psycopg2)
db.connect()
db.create_tables([RcCheckModel])

urls_to_check = []
url_descriptions = []
slack_hook_url = None  # pylint: disable=invalid-name
noisy_messages = False  # pylint: disable=invalid-name


def get_config_data(config: str):
    """
    Extracts the details of a vehicle configuration string.

    Args:
        config (str): The unformatted string containing a vehicle configuration
                        scraped from the website.

    Returns:
        dict: The vehicle details as dict.
    """
    logger.info("Configuration: %s", config)
    pattern = re.compile(r"[a-z][A-Z0-9\$]")
    match = re.search(pattern, config)
    configs = []
    wheels_index = 0
    index = 0
    while match:
        position = match.start() + 1
        index += 1
        if config[:position].endswith("hp"):
            wheels_index = index
        configs.append(config[:position])
        config = config[position:]
        match = re.search(pattern, config)

    if not config.endswith("More"):
        configs.append(config)

    if len(configs) == 0:
        return None

    return {
        "Vehicle": configs[0],
        "Motor/Battery": configs[1],
        "Price": configs[2],
        "Wheels": configs[wheels_index],
        "Interior": configs[wheels_index + 1],
        "Exterior": configs[wheels_index + 2],
        "Packages": ", ".join(configs[(wheels_index + 3):])
    }


def get_config_message(config_dict: dict):
    """
    Generates the message content for a single configuration

    Args:
        config_dict (dict): The dict containing a vehicle configuration

    Returns:
        dict: The message
    """
    message = []
    if len(config_dict) == 0:
        return message

    message.append({
        "type": "divider"
    })
    main_config = {
        "type": "section",
        "fields": []
    }
    for key in list(config_dict.keys())[:3]:
        config_text = config_dict[key] if config_dict[key] else "None"
        field = [
            {"type": "mrkdwn", "text": f"*{key}:*"},
            {"type": "plain_text", "text": f"{config_text}"},
        ]
        main_config["fields"].extend(field)

    message.append(main_config)

    additional_config = {
        "type": "section",
        "fields": []
    }
    for key in list(config_dict.keys())[3:]:
        config_text = config_dict[key] if config_dict[key] else "None"
        field = [
            {"type": "mrkdwn", "text": f"*{key}:*"},
            {"type": "plain_text", "text": f"{config_text}"},
        ]
        additional_config["fields"].extend(field)

    message.append(additional_config)

    return message


def post_message(url, message):
    """ send the message to the designated webhook url

    Args:
        url (string): the destination url
        message (dictionary): the message
    """
    request = Request(url, json.dumps(message).encode('utf-8'))
    try:
        response = urlopen(request)
        response.read()
        logger.info("Message posted")
    except HTTPError as err:
        logger.error("Request failed: %s %s", err.code, err.reason)
    except URLError as err:
        logger.error("Server connection failed: %s", err.reason)


def prepare_and_post_message_to_slack(
    status_code,
    message_text,
    configurations,
    url
):
    """
    Prepare message to slack and then post it.

    Args:
        status_code (int): The status code.
        message_text (str): The message text.
        configurations (dict): The vehicle configurations.
        url (str): The URL.
        url_description (str): The URL description.
    """
    if not url:
        return

    message = {
        "color": "00ff00" if status_code == 200 else "ff0000",
        "text": message_text,
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Rivian Configurations Update" if status_code == 200 else "Rivian Configurations Error"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{message_text}*"
                }
            }
        ]
    }
    for config in configurations:
        message["blocks"].extend(get_config_message(config))

    post_message(url, message)


def handler(event):
    """
    Handles the check of the URL and evaluates if there are any configurations.

    Args:
        event (dict): to supply parameters directly.

    Returns:
        dict: Response Object
    """
    global slack_hook_url, noisy_messages
    logger.debug('event: %s', event)
    urls_to_check.extend(get_env_var_values('URL_TO_CHECK', event))

    if len(urls_to_check) == 0:
        logger.warning("No URLs to check were specified. No processing done.")
        return None

    url_descriptions.extend(get_env_var_values('URL_DESCRIPTION', event))

    logger.debug("urls_to_check: %s", urls_to_check)
    logger.debug("url_descriptions: %s", url_descriptions)

    if len(urls_to_check) > len(url_descriptions):
        logger.warning(
            "Number of URLs to check (%s) does not match the number of URL descriptions (%s).",
            len(urls_to_check),
            len(url_descriptions)
        )

    if 'SLACK_HOOK_URL' in event:
        slack_hook_url = event.SLACK_HOOK_URL
    elif os.getenv('SLACK_HOOK_URL'):
        slack_hook_url = os.getenv('SLACK_HOOK_URL')
    else:
        logger.warning("'SLACK_HOOK_URL' was not specified. Messages will not be sent to Slack.")

    if 'NOISY_MESSAGES' in event:
        noisy_messages = event.NOISY_MESSAGES.lower() == 'true'
    elif os.getenv('NOISY_MESSAGES'):
        noisy_messages = os.getenv('NOISY_MESSAGES').lower() == 'true'

    with ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(task, range(len(urls_to_check)))


def get_env_var_values(env_var_name: str, event):
    """
    Get environment variables values from OS or event object

    Args:
        env_var_name (str): The environment variable name prefix
        event (_type_): The event object

    Returns:
        list: List of environment variable values
    """
    env_var_values = []
    if env_var_name in event:
        env_var_values.append(event.URL_TO_CHECK)
    elif os.getenv(env_var_name):
        env_var_values.append(os.getenv(env_var_name))

    url_index = 1
    while f"{env_var_name}{url_index}" in event or os.getenv(f"{env_var_name}{url_index}"):
        if f"{env_var_name}{url_index}" in event:
            env_var_values.append(event[f"{env_var_name}{url_index}"])
        elif os.getenv(f"{env_var_name}{url_index}"):
            env_var_values.append(os.getenv(f"{env_var_name}{url_index}"))
        url_index += 1

    return env_var_values


def task(number: int):
    """
    Performs the actual work

    Args:
        number (int): task ID
    """
    url = urls_to_check[number]
    url_description = url_descriptions[number] if number < len(url_descriptions) else "No description"
    articles = None
    with sync_playwright() as p:
        logger.info('Launching browser...')
        browser = p.webkit.launch()
        logger.info('Successfully launched browser.')
        logger.info('Retrieving URL [%s]...', url)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_load_state('load')
        time.sleep(3)
        logger.info('Successfully retrieved URL.')

        reload_counter = 0
        while articles is None and reload_counter < 3:
            span_element = page.locator('text="No exact matches"')
            if span_element.count() > 0:
                articles = []

            article_elements = page.locator("[data-testid^='ShopVehicleLink-']")
            config_count = len(article_elements.all())
            if config_count > 0:
                articles = []
                for element in article_elements.all():
                    logger.debug(element.text_content())
                    articles.append(element.text_content())

            if articles is None:
                reload_counter = reload_counter + 1
                page.reload()
                page.wait_for_load_state('load')

        browser.close()

    if articles is None:
        status_code = 500
        message = "URL could not be rendered correctly after multiple reloads."
        logger.error(message)
        prepare_and_post_message_to_slack(
            status_code=status_code,
            message_text=message,
            configurations=None,
            url=slack_hook_url
        )
    else:
        status_code = 200
        configs_count = len(articles)
        if configs_count == 0:
            message = f"No matching configuration was found for {url_description}"
            logger.info(message)
        else:
            message = f"{configs_count} matching configuration{' was' if configs_count == 1 else 's were'} found for {url_description}"
            logger.info(message)

        configurations = []
        for article in articles:
            configurations.append(get_config_data(article))

        record = RcCheckModel.select().where(RcCheckModel.url == url)
        if not record.exists():
            logger.info('No record exists yet for [%s]', url)
            current_time = datetime.now()
            new_record = RcCheckModel.create(
                url=url,
                url_description=url_description,
                created_time=current_time,
                modified_time=current_time,
                last_checked_time=current_time,
                configurations=configurations,
            )
            new_record.save()
            if len(articles) > 0 or noisy_messages:
                prepare_and_post_message_to_slack(
                    status_code=status_code,
                    message_text=message,
                    configurations=configurations,
                    url=slack_hook_url
                )
        else:
            existing_record = record.get()
            number_of_configurations = len(existing_record.configurations)
            logger.info(
                'A record exists with %s configurations',
                number_of_configurations
            )
            current_time = datetime.now()
            if configurations == existing_record.configurations:
                logger.info('No changes; updating last checked time only.')

                existing_record.last_checked_time = current_time
                existing_record.save()

                if noisy_messages:
                    prepare_and_post_message_to_slack(
                        status_code=status_code,
                        message_text=message,
                        configurations=configurations,
                        url=slack_hook_url
                    )
            else:
                logger.info('There were changes to configurations; updating all.')

                existing_record.modified = current_time
                existing_record.last_checked_time = current_time
                existing_record.configurations = configurations
                existing_record.save()

                prepare_and_post_message_to_slack(
                    status_code=status_code,
                    message_text=message,
                    configurations=configurations,
                    url=slack_hook_url
                )


if __name__ == "__main__":
    handler({})
