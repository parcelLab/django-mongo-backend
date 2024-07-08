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
        return "ObjectId" if "ObjectIdField" in connection.data_types else "CHAR(24)"

    def to_python(self, value):
        if value is None or isinstance(value, bson.ObjectId):
            return value
        else:
            return bson.ObjectId(value)

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return bson.ObjectId(value)
        return bson.ObjectId(value)

    def get_db_prep_value(self, value, connection, prepared=False):
        return (
            self.get_prep_value(value) if "ObjectIdField" in connection.data_types else str(value)
        )


class ObjectIdField(ObjectIdFieldMixin, models.CharField):
    pass


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
