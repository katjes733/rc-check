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
from playhouse.postgres_ext import PostgresqlExtDatabase

from apscheduler.schedulers.background import BackgroundScheduler

from flask import Flask

from models.check import RcCheckModel
from models.check_history import RcCheckHistoryModel
from models.check_url import RcCheckUrlsModel

from api.url import create_url_in_db, get_url, get_urls_from_db, url_blueprint


CONST_ENCODING = 'utf-8'
CONST_INCOMPLETE = "Incomplete"
CONST_RED = "#FF0000"
CONST_GREEN = "#00FF00"
CONST_ORANGE = "#FF8C00"
CONST_GRAY = "#808080"
CONST_CREATE_ACTION = "create"
CONST_UPDATE_ACTION = "update"

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


logger.debug(psycopg2)
db.connect()
db.bind([RcCheckModel, RcCheckHistoryModel, RcCheckUrlsModel])
db.create_tables([RcCheckModel, RcCheckHistoryModel, RcCheckUrlsModel])

urls_to_check = []
slack_hook_url = None  # pylint: disable=invalid-name
noisy_messages = False  # pylint: disable=invalid-name

app = Flask(__name__)

app.register_blueprint(url_blueprint, url_prefix='/api')

app_scheduler = BackgroundScheduler()


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

    configs.append(re.sub(r"(\d\+)More", r"\g<1> additional Packages", config))

    if len(configs) == 0:
        return None

    return {
        "Vehicle": configs[0],
        "Motor/Battery": configs[1],
        "Price": configs[2],
        "Wheels": configs[wheels_index] if wheels_index > 0 else CONST_INCOMPLETE,
        "Interior": configs[wheels_index + 1] if wheels_index > 0 else CONST_INCOMPLETE,
        "Exterior": configs[wheels_index + 2] if wheels_index > 0 else CONST_INCOMPLETE,
        "Packages": ", ".join(configs[(wheels_index + 3):] if wheels_index > 0 else [CONST_INCOMPLETE])
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
    slack_request = Request(url, json.dumps(message).encode('utf-8'))
    try:
        response = urlopen(slack_request)
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
    """
    if not url:
        return

    color = CONST_GRAY
    header_text = "Updates to Rivian Configurations"
    if status_code == 200:
        color = CONST_ORANGE
    elif status_code == 201:
        color = CONST_GREEN
        header_text = "New Rivian Configurations"
    elif status_code == 500:
        color = CONST_RED
        header_text = "Error retrieving Rivian configurations"

    message = {
        "attachments": [{
            "fallback": re.sub(r"\<.*?\|(?P<desc>.*?)\>", r"\g<desc>", message_text),
            "color": color,
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": header_text
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
        }]
    }
    for config in configurations:
        message["attachments"][0]["blocks"].extend(get_config_message(config))

    post_message(url, message)


def get_urls_to_check(event) -> list[dict]:
    """
    Gets the URL object to check.
    Considers objects in the DB as well as objects provided
    through environment variables or event object.
    Objects in DB supersede any environment variables.

    Args:
        event (dict): The event object.

    Returns:
        list[dict]: The list of URL objects.
    """
    urls_from_env = get_env_var_values('URL_TO_CHECK', event)
    logger.info(urls_from_env)
    url_descriptions_from_env = get_env_var_values('URL_DESCRIPTION', event)
    logger.info(url_descriptions_from_env)
    url_objects = []
    for index, url in enumerate(urls_from_env):
        if not any(d.get("url") == url for d in url_objects):
            url_description = "No description"
            if index < len(url_descriptions_from_env):
                url_description = url_descriptions_from_env[index]
            url_objects.append({
                "url": url,
                "url_description": url_description,
            })

    for url_object in url_objects:
        url_in_db = get_url(url_object["url"])
        if not url_in_db:
            create_url_in_db(url_object)

    return get_urls_from_db()


def handler(event):
    """
    Handles the check of the URL and evaluates if there are any configurations.
    Args:
        event (dict): to supply parameters directly.

    Returns:
        dict: Response Object
    """
    global slack_hook_url, noisy_messages, urls_to_check
    logger.debug('event: %s', event)

    urls_to_check = get_urls_to_check(event)

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


def is_match_configurations(new: dict, current: dict) -> bool:
    """
    Compares the new configuration (from URL search) with the current
    configuration in the DB.
    If new or current configurations contains any `Incomplete` text, the
    comparison will only take into consideration fields `Vehicle`,
    `Motor/Battery` and `Price` as the unique parameters. These are the only
    values that are guaranteed to be extracted every time a configuration is
    detected on the website.
    In all other cases we do a full dict compare.

    Args:
        new (dict): The new configuration
        current (dict): The current configuration in the DB

    Returns:
        bool: True, if the configurations match; False otherwise
    """
    if len(new) != len(current):
        return False

    if has_incomplete_configuration(new) and \
            not has_incomplete_configuration(current):
        # min compare
        for index, one_new in enumerate(new):
            if one_new["Vehicle"] != current[index]["Vehicle"] or \
                    one_new["Motor/Battery"] != current[index]["Motor/Battery"] or \
                    one_new["Price"] != current[index]["Price"]:
                return False
        return True

    # full compare
    return new == current


def has_incomplete_configuration(configurations: dict) -> bool:
    """
    Identifies if a set of configurations contain incomplete data.

    Args:
        configurations (dict): The dict of configurations.

    Returns:
        bool: True, if there is an incomplete configuration; false otherwise.
    """
    return f'"{CONST_INCOMPLETE}"' in json.dumps(configurations)


def task(number: int):
    """
    Performs the actual work

    Args:
        number (int): task ID
    """
    url = urls_to_check[number]["url"]
    url_description = urls_to_check[number]["url_description"]
    configurations = None
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
        while configurations is None and reload_counter < 3:
            span_element = page.locator('text="No exact matches"')
            if span_element.count() > 0:
                configurations = []

            article_elements = page.locator("[data-testid^='ShopVehicleLink-']")
            config_count = len(article_elements.all())
            if config_count > 0:
                configurations = []
                for element in article_elements.all():
                    configurations.append(get_config_data(element.text_content()))

            if configurations is None or has_incomplete_configuration(configurations):
                reload_counter = reload_counter + 1
                page.reload()
                page.wait_for_load_state('load')

        browser.close()

    if configurations is None:
        status_code = 500
        message = f"<{url}|URL> could not be rendered correctly after multiple reloads."
        logger.error(message)
        prepare_and_post_message_to_slack(
            status_code=status_code,
            message_text=message,
            configurations=None,
            url=slack_hook_url
        )
    else:
        status_code = 200
        configs_count = len(configurations)
        if configs_count == 0:
            message = f"No matching configuration was found for <{url}|{url_description}>"
            logger.info(message)
        else:
            message = f"{configs_count} matching configuration{' was' if configs_count == 1 else 's were'} found for <{url}|{url_description}>"
            logger.info(message)

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
            new_history_record = RcCheckHistoryModel.create(
                url=url,
                modified_time=current_time,
                modified_action=CONST_CREATE_ACTION,
                url_description=url_description,
                configurations=configurations,
            )
            new_history_record.save()
            status_code = 201
            if len(configurations) > 0 or noisy_messages:
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
            if is_match_configurations(
                        new=configurations,
                        current=existing_record.configurations
                    ):
                logger.info('No changes; updating last checked time only.')

                existing_record.last_checked_time = current_time
                existing_record.save()
                insert_previous_history_record(
                    url=url,
                    url_description=url_description,
                    configurations=configurations,
                    current_time=current_time,
                    existing_record=existing_record
                )

                if noisy_messages:
                    prepare_and_post_message_to_slack(
                        status_code=status_code,
                        message_text=message,
                        configurations=configurations,
                        url=slack_hook_url
                    )
            else:
                logger.info('There were changes to configurations; updating all.')

                insert_previous_history_record(
                    url=url,
                    url_description=url_description,
                    configurations=configurations,
                    current_time=current_time,
                    existing_record=existing_record
                )

                existing_record.modified_time = current_time
                existing_record.last_checked_time = current_time
                existing_record.configurations = configurations
                existing_record.save()

                new_history_record = RcCheckHistoryModel.create(
                    url=url,
                    modified_time=current_time,
                    modified_action=CONST_UPDATE_ACTION,
                    url_description=url_description,
                    configurations=configurations,
                )
                new_history_record.save()

                prepare_and_post_message_to_slack(
                    status_code=status_code,
                    message_text=message,
                    configurations=configurations,
                    url=slack_hook_url
                )


def insert_previous_history_record(
        url: str,
        url_description: str,
        configurations: dict,
        current_time,
        existing_record: dict):
    """
    In case there is no existing history, a new history is inserted based on
    the existing record.
    This method should be used for update cases only, as it required an
    existing record as input.

    Args:
        url (str): The search URL.
        url_description (str): The search URL description.
        configurations (dict): The configurations.
        current_time (_type_): The current time.
        existing_record (dict): The existing record.
    """
    history_record = RcCheckHistoryModel.select().where(
        (RcCheckHistoryModel.url == existing_record.url) &
        (RcCheckHistoryModel.modified_time == existing_record.modified_time)
    )
    if not history_record.exists():
        modified_time = current_time
        modified_action = CONST_UPDATE_ACTION
        if existing_record.modified_time == existing_record.created_time:
            modified_time = existing_record.created_time
            modified_action = CONST_CREATE_ACTION

        new_history_record = RcCheckHistoryModel.create(
            url=url,
            modified_time=modified_time,
            modified_action=modified_action,
            url_description=url_description,
            configurations=configurations,
        )
        new_history_record.save()


if __name__ == "__main__":
    app_scheduler.add_job(handler, 'interval', minutes=1, args=[{}])
    app_scheduler.start()
    app.run(port=5000, debug=os.getenv('DEBUG', 'false').lower() == 'true')
    app_scheduler.shutdown()
