"""
Entity fo RC Check History.
"""
from datetime import datetime
from peewee import Model, TextField, CompositeKey
from playhouse.postgres_ext import BinaryJSONField, DateTimeTZField


class RcCheckHistoryModel(Model):
    """
    Entity fo RC Check History.
    Contains historic data of RC Check

    Args:
        Model (Model): The Model
    """
    url = TextField(null=False)
    modified_time = DateTimeTZField(null=False, default=datetime.now)
    modified_action = TextField(null=False)
    url_description = TextField(null=True)
    configurations = BinaryJSONField(default=[])

    class Meta:
        """
        Meta data
        """
        table_name = 'rc_check_history'
        primary_key = CompositeKey('url', 'modified_time')
