import datetime

from bson import ObjectId
from django.db.backends.base.operations import BaseDatabaseOperations


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "django_mongodb.compiler"

    def quote_name(self, name):
        if name.startswith('"') and name.endswith('"'):
            return name
        return f'"{name}"'

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        return [{"op": "flush", "collection": table} for table in tables]

    def execute_sql_flush(self, sql_list):
        with self.connection.cursor() as conn:
            for sql in sql_list:
                if sql["op"] == "flush":
                    conn.connection.drop_collection(sql["collection"])

    def pk_default_value(self):
        return ObjectId()

    def adapt_json_value(self, value, encoder):
        return value

    def adapt_datetimefield_value(self, value):
        return value

    def adapt_timefield_value(self, value: datetime.time):
        if isinstance(value, datetime.time):
            return datetime.datetime.combine(datetime.date(2000, 1, 1), value)
        else:
            return value

    def adapt_datefield_value(self, value):
        if isinstance(value, datetime.date):
            return datetime.datetime(value.year, value.month, value.day)
        else:
            return value

    def convert_time_value(self, value, expression, connection):
        if isinstance(value, datetime.datetime):
            return value.time()
        return value

    def convert_date_value(self, value, expression, connection):
        if isinstance(value, datetime.datetime):
            return value.date()
        return value

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        match internal_type:
            case "TimeField":
                converters.append(self.convert_time_value)
            case "DateField":
                converters.append(self.convert_date_value)
        return converters
