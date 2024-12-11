"""
Check API for checks

Provides Get, Create, Delete and Update functionality.
"""
from datetime import datetime
from flask import Blueprint, jsonify, request, Response

from playhouse.shortcuts import model_to_dict

from peewee import IntegrityError

from models.check import RcCheckModel

check_blueprint = Blueprint('check_blueprint', __name__)


def get_check_for_url_from_db(url: str) -> RcCheckModel:
    """
    Gets a check record for a given URL from the DB.

    Args:
        url (str): The URL identifying the check.

    Returns:
        RcCheckModel: The check object or None if not found.
    """
    query = RcCheckModel.select().where(RcCheckModel.url == url)
    return query.get_or_none()


@check_blueprint.route('/check/<string:url>', methods=['GET'])
def get_check_for_url(url: str) -> Response:
    """
    Gets a check record for a given URL.

    Args:
        url (str): The URL identifying the check.

    Returns:
        Response: Returns a dict for type RcCheckModel
    """
    result = get_check_for_url_from_db(url)
    if not result:
        return jsonify(
            {"error": "Check for "
                f"[{url}] "
                "does not exist."}
        ), 404
    return jsonify(model_to_dict(result)), 200
