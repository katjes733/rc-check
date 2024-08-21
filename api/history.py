"""
History API for checks
"""
from flask import Blueprint, jsonify, request, Response

from playhouse.shortcuts import model_to_dict

from datetime import datetime

from models.check_history import RcCheckHistoryModel

history_blueprint = Blueprint('history_blueprint', __name__)


def get_history_for_url_from_db(url: str) -> list[RcCheckHistoryModel]:
    """
    Gets all history entries for a given URL

    Args:
        url (str): The URL

    Returns:
        list[RcCheckHistoryModel]: The list of History dict
    """
    query = RcCheckHistoryModel.select().\
        where(RcCheckHistoryModel.url == url).\
        order_by(RcCheckHistoryModel.modified_time.desc())
    return [model_to_dict(h) for h in query]


@history_blueprint.route('/history/<string:url', methods=['GET'])
def get_history_for_url(url: str) -> Response:
    """
    Gets all history entries for a given URL.

    Args:
        url (str): The URL

    Returns:
        Response: Returns an array of dict for type RcCheckHistoryModel
    """
    return jsonify(get_history_for_url_from_db(url)), 200


def get_history_for_url_and_modified_time_from_db(
        url: str,
        modified_time: datetime) -> RcCheckHistoryModel:
    """
    Gets a single History by URL and modified time or None from DB.
    If modified_time is None, the latest history entry is returned if it
    exists. Otherwise None.

    Args:
        url (str): The URL
        modified_time (datetime): The modified time or None

    Returns:
        RcCheckHistoryModel: A single history entry or None.
    """
    if modified_time:
        query = RcCheckHistoryModel.select().where(
            (RcCheckHistoryModel.url == url) &
            (RcCheckHistoryModel.modified_time == modified_time)
        )
        return model_to_dict(query.get_or_none())
    results = get_history_for_url_from_db(url)
    if len(results) > 0:
        return results[0]
    return None


@history_blueprint.route('/history', methods=['GET'])
def get_history_for_url_and_modified_time() -> Response:
    """
    Gets a single History by URL and modified time or None.

    Returns:
        Response: Returns an array of dict for type RcCheckHistoryModel.
                  Returns error if not found or otherwise.
    """
    history_data = request.get_json()
    if "url" not in history_data:
        return jsonify({
            "error": "Property 'url' not provided."
        }), 400
    modified_time = None
    if "modified_time" in history_data:
        modified_time = history_data["modified_time"]
    result = get_history_for_url_and_modified_time_from_db(history_data["url"], modified_time)
    if not result:
        return jsonify(
            {"error": f"History for [{history_data["url"]}] "
                "and modified time [{modified_time}] does not exist."}
        ), 404
    return jsonify(result), 200
