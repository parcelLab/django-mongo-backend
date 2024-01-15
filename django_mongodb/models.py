import bson
from django.db import models
from django.db.models.fields import AutoField, AutoFieldMeta
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _


class ObjectIdFieldMixin:
    description = "MongoDB ObjectIdField"
    default_error_messages = {
        "invalid": _("“%(value)s” value must be an ObjectId."),
    }

    @cached_property
    def validators(self):
        return self._validators

    def db_type(self, connection):
        return "ObjectId"

    def to_python(self, value):
        if value is None or isinstance(value, bson.ObjectId):
            return value
        else:
            return bson.ObjectId(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return bson.ObjectId(value)
        return bson.ObjectId(value)


class ObjectIdField(ObjectIdFieldMixin, models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 24
        super().__init__(*args, **kwargs)


class ObjectIdAutoField(ObjectIdFieldMixin, AutoField, metaclass=AutoFieldMeta):
    description = "MongoDB ObjectIdAutoField"

    def __init__(self, *args, **kwargs):
        if "db_column" not in kwargs:
            kwargs["db_column"] = "_id"
        super().__init__(*args, **kwargs)

    def get_internal_type(self):
        return "ObjectIdAutoField"

    def rel_db_type(self, connection):
        return ObjectIdField().db_type(connection=connection)
