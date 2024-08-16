"""
URL API
"""
from flask import Blueprint, jsonify, request

from playhouse.shortcuts import model_to_dict

from models.check_url import RcCheckUrlsModel

url_blueprint = Blueprint('url_blueprint', __name__)


@url_blueprint.route('/urls', methods=['GET'])
def get_urls():
    """
    Gets all the URLs

    Returns:
        dict: Returns an array of dict for type RcCheckUrlsModel
    """
    query = RcCheckUrlsModel.select()
    results = [model_to_dict(r) for r in query]
    return jsonify(results)


def get_url(url: str):
    """
    Gets a single URL.

    Args:
        url (str): The URL to get.

    Returns:
        dict: The URL or none if not found
    """
    query = RcCheckUrlsModel.select().where(RcCheckUrlsModel.url == url)
    return query.get_or_none()


@url_blueprint.route('/urls/<string:url>', methods=['DELETE'])
def delete_url(url: str):
    """
    Deletes an URl

    Args:
        url (str): The URL to delete.

    Returns:
        dict: The deleted URL.
    """
    existing_url = get_url(url)
    if not existing_url:
        return jsonify({"error": f"URL [{url}] does not exist."}), 404

    existing_url.delete_instance()
    return jsonify(model_to_dict(existing_url)), 200


@url_blueprint.route('/urls', methods=['POST'])
def create_url(data=None):
    """
    Creates an URL. Data can be passed in as function
    parameter or as request payload.

    Args:
        data (dict, optional): The data. Defaults to None.

    Returns:
        dict: The created URL object.
    """
    if data is None:
        data = {}
    url_data = {}
    if data and RcCheckUrlsModel.url.name in data and RcCheckUrlsModel.url_description.name in data:
        url_data[RcCheckUrlsModel.url.name] = data[RcCheckUrlsModel.url.name]
        url_data[RcCheckUrlsModel.url_description.name] = data[RcCheckUrlsModel.url_description.name]
    else:
        tmp_data = request.get_json()
        if tmp_data and RcCheckUrlsModel.url.name in tmp_data and RcCheckUrlsModel.url_description.name in tmp_data:
            url_data[RcCheckUrlsModel.url.name] = tmp_data[RcCheckUrlsModel.url.name]
            url_data[RcCheckUrlsModel.url_description.name] = tmp_data[RcCheckUrlsModel.url_description.name]
    if not url_data:
        return jsonify({"error": "Invalid URL properties."}), 400
    existing_url = get_url(url_data[RcCheckUrlsModel.url.name])
    if existing_url:
        return jsonify({"error": f"URL [{url_data[RcCheckUrlsModel.url.name]}] already exists."}), 404
    new_url = RcCheckUrlsModel.create(
        url=url_data[RcCheckUrlsModel.url.name],
        url_description=url_data[RcCheckUrlsModel.url_description.name],
    )
    new_url.save()
    return jsonify(model_to_dict(new_url)), 200


@url_blueprint.route('/urls/<string:url>', methods=['PUT'])
def update_url(url: str, data=None):
    """
    Update an URL. Data can be passed as function parameter
    or as request payload.

    Args:
        url (str): The URL.
        data (dict, optional): The data. Defaults to None.

    Returns:
        dict: The updated URL object.
    """
    if data is None:
        data = {}
    url_data = {}
    if data and RcCheckUrlsModel.url_description.name in data:
        url_data[RcCheckUrlsModel.url_description.name] = data[RcCheckUrlsModel.url_description.name]
    else:
        tmp_data = request.get_json()
        if tmp_data and RcCheckUrlsModel.url_description.name in tmp_data:
            url_data[RcCheckUrlsModel.url_description.name] = tmp_data[RcCheckUrlsModel.url_description.name]
    if not url_data:
        return jsonify({"error": "Invalid URL properties."}), 400
    updated_url = get_url(url)
    if not updated_url:
        return jsonify({"error": f"URL [{url}] does not exist."}), 404
    updated_url.url_description = url_data[RcCheckUrlsModel.url_description.name]
    updated_url.save()
    return jsonify(model_to_dict(updated_url)), 200
