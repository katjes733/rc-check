"""
Entity for Check URL
"""

from peewee import Model, TextField


class RcCheckUrlsModel(Model):
    """
    Entity for Check URL

    Args:
        Model (Model): The Model.
    """
    url = TextField(primary_key=True, null=False)
    url_description = TextField(null=True)

    class Meta:
        """
        Meta data
        """
        table_name = 'rc_check_urls'
