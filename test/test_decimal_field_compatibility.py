"""
Tests to ensure DecimalField compatibility across Django versions.
For Django < 5.2, we need to use the custom DecimalField from django_mongodb.
For Django >= 5.2, the built-in DecimalField should work correctly.
"""

from decimal import Decimal

import django
import pytest
from django.db import models

from django_mongodb.models import DecimalField as MongoDecimalField


# Test model using built-in Django DecimalField
class BuiltinDecimalModel(models.Model):
    value = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        app_label = "testapp"
        db_table = "test_builtin_decimal"


# Test model using custom MongoDB DecimalField
class MongoDecimalModel(models.Model):
    value = MongoDecimalField(max_digits=10, decimal_places=2)

    class Meta:
        app_label = "testapp"
        db_table = "test_mongo_decimal"


@pytest.mark.django_db(databases=["mongodb"])
def test_custom_decimal_field_always_works():
    """Custom MongoDB DecimalField should work on all Django versions."""
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
    Built-in DecimalField should work on Django >= 5.2.
    For Django < 5.2, this test demonstrates the issue that requires
    using the custom DecimalField.
    """
    django_version = tuple(map(int, django.__version__.split(".")[:2]))

    # Create and save (this should always work)
    obj = BuiltinDecimalModel(value=Decimal("456.78"))
    obj.save()

    # Retrieve (this should always work)
    retrieved = BuiltinDecimalModel.objects.get(pk=obj.pk)
    assert retrieved.value == Decimal("456.78")

    # Filter - this is where the issue occurs on Django < 5.2
    if django_version >= (5, 2):
        # On Django 5.2+, built-in DecimalField should work
        filtered = BuiltinDecimalModel.objects.filter(value=Decimal("456.78"))
        assert filtered.count() == 1
    else:
        # On Django < 5.2, filtering with built-in DecimalField fails
        # with BSON encoding error
        with pytest.raises(Exception) as exc_info:
            list(BuiltinDecimalModel.objects.filter(value=Decimal("456.78")))
        assert "cannot encode object" in str(exc_info.value) or "Decimal" in str(exc_info.value)

    # Cleanup
    BuiltinDecimalModel.objects.all().delete()


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_recommendation():
    """
    This test documents the recommended approach for different Django versions.
    """
    django_version = tuple(map(int, django.__version__.split(".")[:2]))

    if django_version >= (5, 2):
        # For Django 5.2+, both should work
        recommendation = "Django >= 5.2: You can use either django.db.models.DecimalField or django_mongodb.models.DecimalField"
    else:
        # For Django < 5.2, custom field is required
        recommendation = "Django < 5.2: You must use django_mongodb.models.DecimalField for proper MongoDB compatibility"

    # This assertion always passes - it's just to document the recommendation
    assert recommendation is not None

    # Verify the recommendation by testing both fields
    test_value = Decimal("999.99")

    # Custom field should always work
    mongo_obj = MongoDecimalModel.objects.create(value=test_value)
    assert MongoDecimalModel.objects.filter(value=test_value).count() == 1
    mongo_obj.delete()

    # Built-in field behavior depends on Django version
    builtin_obj = BuiltinDecimalModel.objects.create(value=test_value)
    if django_version >= (5, 2):
        assert BuiltinDecimalModel.objects.filter(value=test_value).count() == 1
    else:
        try:
            # This will fail on Django < 5.2
            list(BuiltinDecimalModel.objects.filter(value=test_value))
            raise AssertionError("Expected BSON encoding error on Django < 5.2")
        except Exception as e:
            assert "cannot encode object" in str(e) or "Decimal" in str(e)
    builtin_obj.delete()
