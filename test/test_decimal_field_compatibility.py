"""
Tests to ensure DecimalField compatibility across Django versions.
For Django < 5.2, we need to use the custom DecimalField from django_mongodb.
For Django >= 5.2, the built-in DecimalField should work correctly.
"""

from decimal import Decimal

import pytest
from django.db import models
from django_mongodb_backend.fields import ObjectIdAutoField

# The official django-mongodb-backend handles DecimalField natively
# No need to import custom DecimalField


# Test model using built-in Django DecimalField
class BuiltinDecimalModel(models.Model):
    id = ObjectIdAutoField(primary_key=True)
    value = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        app_label = "testapp"
        db_table = "test_builtin_decimal"


# Test model using Django's DecimalField (same as above, for compatibility testing)
class MongoDecimalModel(models.Model):
    id = ObjectIdAutoField(primary_key=True)
    value = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        app_label = "testapp"
        db_table = "test_mongo_decimal"


@pytest.mark.django_db(databases=["mongodb"])
def test_custom_decimal_field_always_works():
    """Django's DecimalField should work with the official django-mongodb-backend."""
    # Create and save
    obj = MongoDecimalModel(value=Decimal("123.45"))
    obj.save()

    # Retrieve
    retrieved = MongoDecimalModel.objects.get(pk=obj.pk)
    assert retrieved.value == Decimal("123.45")

    # Filter
    filtered = MongoDecimalModel.objects.filter(value=Decimal("123.45"))
    assert filtered.count() == 1

    # Cleanup
    MongoDecimalModel.objects.all().delete()


@pytest.mark.django_db(databases=["mongodb"])
def test_builtin_decimal_field_compatibility():
    """
    Built-in DecimalField should work with the official django-mongodb-backend.
    """
    # Create and save
    obj = BuiltinDecimalModel(value=Decimal("456.78"))
    obj.save()

    # Retrieve
    retrieved = BuiltinDecimalModel.objects.get(pk=obj.pk)
    assert retrieved.value == Decimal("456.78")

    # Filter - should work with the official backend
    filtered = BuiltinDecimalModel.objects.filter(value=Decimal("456.78"))
    assert filtered.count() == 1

    # Cleanup
    BuiltinDecimalModel.objects.all().delete()


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_recommendation():
    """
    Test that Django's built-in DecimalField works with the official django-mongodb-backend.
    """
    # With the official backend, Django's DecimalField should work on all supported versions
    test_value = Decimal("999.99")

    # Test with both model variants (they use the same field type now)
    mongo_obj = MongoDecimalModel.objects.create(value=test_value)
    assert MongoDecimalModel.objects.filter(value=test_value).count() == 1
    mongo_obj.delete()

    builtin_obj = BuiltinDecimalModel.objects.create(value=test_value)
    assert BuiltinDecimalModel.objects.filter(value=test_value).count() == 1
    builtin_obj.delete()
