from django.db.backends.base.base import BaseDatabaseWrapper
from pymongo import MongoClient

import django_mongodb.database as Database
from django_mongodb.client import DatabaseClient
from django_mongodb.creation import DatabaseCreation
from django_mongodb.cursor import Cursor
from django_mongodb.features import DatabaseFeatures
from django_mongodb.introspection import DatabaseIntrospection
from django_mongodb.operations import DatabaseOperations
from django_mongodb.schema import DatabaseSchemaEditor


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = "django_mongodb"
    data_types = {
        "JSONField": "json",
        "ObjectIdField": "objectid",
        "ObjectIdAutoField": "objectid",
        "AutoField": "integer",
        "BigAutoField": "bigint",
        "BinaryField": "binary",
        "BooleanField": "boolean",
        "CharField": "string",
        "DateField": "date",
        "DateTimeField": "timestamp with time zone",
        "DecimalField": "decimal128",
        "DurationField": "interval",
        "FileField": "varchar(%(max_length)s)",
        "FilePathField": "varchar(%(max_length)s)",
        "FloatField": "double precision",
        "IntegerField": "integer",
        "BigIntegerField": "bigint",
        "IPAddressField": "inet",
        "GenericIPAddressField": "inet",
        "OneToOneField": "integer",
        "PositiveBigIntegerField": "bigint",
        "PositiveIntegerField": "integer",
        "PositiveSmallIntegerField": "smallint",
        "SlugField": "varchar(%(max_length)s)",
        "SmallAutoField": "smallint",
        "SmallIntegerField": "smallint",
        "TextField": "text",
        "TimeField": "time",
        "UUIDField": "uuid",
    }
    data_type_check_constraints = {
        "PositiveBigIntegerField": '"%(column)s" >= 0',
        "PositiveIntegerField": '"%(column)s" >= 0',
        "PositiveSmallIntegerField": '"%(column)s" >= 0',
    }
    data_types_suffix = {
        "AutoField": "GENERATED BY DEFAULT AS IDENTITY",
        "BigAutoField": "GENERATED BY DEFAULT AS IDENTITY",
        "SmallAutoField": "GENERATED BY DEFAULT AS IDENTITY",
    }
    operators = {
        "exact": "= %s",
        "iexact": "= UPPER(%s)",
        "contains": "LIKE %s",
        "icontains": "LIKE UPPER(%s)",
        "regex": "~ %s",
        "iregex": "~* %s",
        "gt": "> %s",
        "gte": ">= %s",
        "lt": "< %s",
        "lte": "<= %s",
        "startswith": "LIKE %s",
        "endswith": "LIKE %s",
        "istartswith": "LIKE UPPER(%s)",
        "iendswith": "LIKE UPPER(%s)",
    }

    connection: MongoClient = None

    SchemaEditorClass = DatabaseSchemaEditor
    # Classes instantiated in __init__().
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations

    Database = Database

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mongo_client = None

    def get_connection_params(self):
        return self.settings_dict

    def get_new_connection(self, conn_params):
        name = conn_params.get("NAME") or "test"
        connection_params = conn_params.get("CLIENT")

        if self.mongo_client is not None:
            self.mongo_client.close()
            self.mongo_client = None

        self.mongo_client = MongoClient(**connection_params, connect=False)
        return self.mongo_client[name]

    def get_database_version(self):
        return self.connection.server_info()["version"]

    def create_cursor(self, name=None):
        return Cursor(self.mongo_client, self.connection)

    def _close(self):
        if self.mongo_client is not None:
            with self.wrap_database_errors:
                self.mongo_client.close()

    def rollback(self):
        pass

    def _set_autocommit(self, autocommit):
        pass

    def commit(self):
        pass