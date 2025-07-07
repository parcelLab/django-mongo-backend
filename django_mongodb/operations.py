import datetime
from decimal import Decimal

from bson import ObjectId
from bson.decimal128 import Decimal128
from django.conf import settings
from django.db.backends.base.operations import BaseDatabaseOperations
from django.utils.timezone import is_aware, make_aware


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

    def convert_datetime_value(self, value, expression, connection):
        if settings.USE_TZ and isinstance(value, datetime.datetime) and not is_aware(value):
            return make_aware(value)
        return value

    def convert_decimalfield_value(self, value, expression, connection):
        """
        Convert BSON Decimal128 back to Python Decimal.
        Also handles string values for backward compatibility.
        """
        if value is None:
            return None

        # If it's a Decimal128, convert to Python Decimal
        if isinstance(value, Decimal128):
            return value.to_decimal()

        # If it's a string, convert to Decimal
        if isinstance(value, str):
            return Decimal(value)

        # If it's already a Decimal, return as is
        if isinstance(value, Decimal):
            return value

        # Fallback to Decimal conversion
        return Decimal(str(value))

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        match internal_type:
            case "TimeField":
                converters.append(self.convert_time_value)
            case "DateField":
                converters.append(self.convert_date_value)
            case "DateTimeField":
                converters.append(self.convert_datetime_value)
            case "DecimalField":
                converters.append(self.convert_decimalfield_value)
        return converters

    def adapt_decimalfield_value(self, value, max_digits=None, decimal_places=None):
        """
        Transform a decimal.Decimal value to a BSON Decimal128 object.
        """
        if value is None:
            return None

        # If it's already a Decimal128, return as is
        if isinstance(value, Decimal128):
            return value

        # Convert to Decimal if it's a string
        if isinstance(value, str):
            value = Decimal(value)

        # Convert Python Decimal to BSON Decimal128
        if isinstance(value, Decimal):
            return Decimal128(str(value))

        # Fallback to string representation
        return Decimal128(str(value))
