"""
URL API
"""
from flask import Blueprint, jsonify, request, Response

from playhouse.shortcuts import model_to_dict

from peewee import IntegrityError

from models.check_url import RcCheckUrlsModel

url_blueprint = Blueprint('url_blueprint', __name__)


def get_urls_from_db() -> list[RcCheckUrlsModel]:
    """
    Gets all URLs from the DB.

    Returns:
        list[RcCheckUrlsModel]: Array of URL dict
    """
    query = RcCheckUrlsModel.select()
    return [model_to_dict(r) for r in query]


@url_blueprint.route('/urls', methods=['GET'])
def get_urls() -> Response:
    """
    Gets all the URLs

    Returns:
        Response: Returns an array of dict for type RcCheckUrlsModel
    """
    return jsonify(get_urls_from_db())


def get_url(url: str) -> RcCheckUrlsModel:
    """
    Gets a single URL.

    Args:
        url (str): The URL to get.

    Returns:
        RcCheckUrlsModel: The URL or none if not found
    """
    query = RcCheckUrlsModel.select().where(RcCheckUrlsModel.url == url)
    return query.get_or_none()


def delete_url_from_db(url: str) -> dict:
    """
    Deletes an URL from the DB if it exists.

    Args:
        url (str): The URL

    Returns:
        dict: The deleted URL dict
    """
    existing_url = get_url(url)
    if not existing_url:
        return None
    existing_url.delete_instance()
    return model_to_dict(existing_url)


@url_blueprint.route('/urls/<string:url>', methods=['DELETE'])
def delete_url(url: str):
    """
    Deletes an URL

    Args:
        url (str): The URL to delete.

    Returns:
        dict: The deleted URL.
    """
    deleted_url = delete_url_from_db(url)
    if not deleted_url:
        return jsonify({"error": f"URL [{url}] does not exist."}), 404
    return jsonify(deleted_url), 200


def create_url_in_db(data: dict) -> dict:
    """
    Creates an URL record in the DB.

    Args:
        data (dict): The data dict.

    Returns:
        dict: The created URL dict or a dict with the error.
    """
    try:
        created_url = RcCheckUrlsModel.create(**data)
        created_url.save()
        return model_to_dict(created_url)
    except IntegrityError as e:
        return {"error": str(e)}


@url_blueprint.route('/urls', methods=['POST'])
def create_url():
    """
    Creates an URL. Data can be passed in as function
    parameter or as request payload.

    Args:
        data (dict, optional): The data. Defaults to None.

    Returns:
        dict: The created URL object.
    """
    url_data = request.get_json()
    created_url = create_url_in_db(url_data)
    if "error" in created_url and "duplicate key" in created_url["error"]:
        return jsonify({
            "error": f"URL [{url_data[RcCheckUrlsModel.url.name]}] "
            "already exists.",
            "details": created_url["error"],
        }), 404
    if "error" in created_url and \
            "Failing row contains" in created_url["error"]:
        return jsonify({
            "error": "Invalid URL properties.",
            "details": created_url["error"],
        }), 400
    return jsonify(created_url), 200


def update_url_in_db(data: dict) -> dict:
    """
    Updates a record in the DB.

    Args:
        data (dict): the URL data object

    Returns:
        dict: The updated URL data object.
    """
    if "url" not in data:
        return {"error": "Object contains no mandatory element 'url'."}
    updated_url = get_url(data["url"])
    if not updated_url:
        return {"error": f"URL [{data['url']}] does not exist."}
    for key, value in data.items():
        if hasattr(updated_url, key):
            setattr(updated_url, key, value)
    updated_url.save()
    return model_to_dict(updated_url)


@url_blueprint.route('/urls/<string:url>', methods=['PUT'])
def update_url(url: str):
    """
    Update an URL. Data can be passed as function parameter
    or as request payload.

    Args:
        url (str): The URL.
        data (dict, optional): The data. Defaults to None.

    Returns:
        dict: The updated URL object.
    """
    data = request.get_json()
    data["url"] = url
    updated_url = update_url_in_db(data)
    if "error" in updated_url and "Object contains no" in updated_url["error"]:
        return jsonify(updated_url), 400
    if "error" in updated_url and "does not exist" in updated_url["error"]:
        return jsonify(updated_url), 404
    return jsonify(updated_url), 200
