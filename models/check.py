"""
    Entity for RC Check.
"""
from datetime import datetime
from peewee import Model, TextField
from playhouse.postgres_ext import BinaryJSONField, DateTimeTZField


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
        table_name = 'rc_check'
