from django.db import models


class DecimalField(models.DecimalField):
    """
    Custom DecimalField that properly converts Python Decimal to BSON Decimal128
    for MongoDB operations.

    This custom field is required for Django < 5.2 to ensure proper conversion
    of Decimal values during query operations. Starting from Django 5.2, the
    built-in DecimalField should handle this conversion automatically.

    Note: When Django 5.2+ is the minimum supported version, this custom field
    can be deprecated in favor of Django's built-in DecimalField.
    """

    def get_db_prep_value(self, value, connection, prepared=False):
        value = super().get_db_prep_value(value, connection, prepared)
        if hasattr(connection.ops, "adapt_decimalfield_value"):
            return connection.ops.adapt_decimalfield_value(
                value, max_digits=self.max_digits, decimal_places=self.decimal_places
            )
        return value
