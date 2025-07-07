import datetime
import os
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128
from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import models
from django.utils.timezone import now
from pymongo import MongoClient

from django_mongodb.expressions import RawMongoDBQuery
from django_mongodb.query import RequiresSearchIndex
from refapp.models import RefModel
from testapp.models import (
    DecimalFieldModel,
    DifferentTableOneToOne,
    FooModel,
    RelatedModel,
    SameTableChild,
    SameTableOneToOne,
)


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_model():
    fixed_now = now().replace(microsecond=0)
    item = FooModel.objects.create(
        name="test",
        json_field={"foo": "bar"},
    )
    assert item.id is not None
    FooModel.objects.filter(name="test").update(
        datetime_field=fixed_now,
        date_field=fixed_now.date(),
        time_field=fixed_now.time(),
    )
    item.refresh_from_db()
    assert item.json_field == {"foo": "bar"}
    assert item.name == "test"
    assert isinstance(item.datetime_field, datetime.datetime)
    assert item.datetime_field == fixed_now
    assert item.date_field == fixed_now.date()
    assert item.time_field == fixed_now.time()


@pytest.mark.django_db(databases=["mongodb"])
def test_db_prep():
    item = FooModel.objects.create(
        name="test",
        json_field={"foo": "bar"},
    )
    assert len(FooModel.objects.filter(id=str(item.id)).all()) == 1


@pytest.mark.django_db(databases=["mongodb"])
def test_datatime_load_save():
    fixed_now = now()
    fixed_now = fixed_now.replace(microsecond=0)  # Mongo does not support this resolution
    item = FooModel.objects.create(
        name="test",
    )
    item.datetime_field = fixed_now
    item.save()
    item = FooModel.objects.get(pk=item.pk)
    assert item.datetime_field.tzinfo is not None
    assert str(item.datetime_field) == str(fixed_now)
    item.save()


@pytest.mark.django_db(databases=["mongodb"])
def test_manager_methods():
    item1 = FooModel.objects.get_or_create(name="test", defaults={"json_field": {"foo": "bar"}})
    item2 = FooModel.objects.get_or_create(name="test", defaults={"json_field": {"foo": "bar"}})
    assert item1[0] is not None
    assert item1[0].id == item2[0].id


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_emtpy():
    assert len(list(FooModel.objects.none())) == 0


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_lookup():
    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    FooModel.objects.create(name="test2", json_field={"foo": "bar"})

    assert len(list(FooModel.objects.filter(datetime_field__gt=now() - timedelta(hours=1)))) == 2
    assert len(list(FooModel.objects.filter(name="test"))) == 1


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_int_isnull():
    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    assert len(list(FooModel.objects.filter(int_field__isnull=True))) == 0
    assert len(list(FooModel.objects.filter(name2__isnull=True))) == 1

    assert len(list(FooModel.objects.exclude(int_field__isnull=True))) == 1
    assert len(list(FooModel.objects.exclude(name2__isnull=True))) == 0


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_model_all_delete():
    FooModel.objects.create(
        name="test",
        json_field={"foo": "bar"},
    )
    FooModel.objects.create(
        name="test2",
        json_field={"foo": "bar"},
    )
    items = FooModel.objects.all()
    assert len(items) == 2
    assert items.delete() == (2, {"testapp.SameTableOneToOne": 2})
    assert FooModel.objects.all().count() == 0


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_model_filter_delete():
    FooModel.objects.all().delete()
    item = FooModel.objects.create(
        name="test",
        json_field={"foo": "bar"},
    )
    item2 = FooModel.objects.create(
        name="test2",
        json_field={"foo": "bar"},
    )
    items = list(FooModel.objects.filter(name="test").all())
    assert len(items) == 1
    item.delete()
    assert list(FooModel.objects.all()) == [item2]


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_model_values():
    FooModel.objects.all().delete()
    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    item_values = list(FooModel.objects.values("name"))
    assert item_values[0]["name"] == "test"


@pytest.mark.django_db(databases=["mongodb"])
def test_nested_value():
    FooModel.objects.all().delete()
    model = FooModel.objects.create(name="test", nested_field="test")
    model.refresh_from_db()
    assert model.nested_field == "test"


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_same_collection_inheritance():
    FooModel.objects.all().delete()
    obj = SameTableChild.objects.create(name="test", json_field={"foo": "bar"}, extended="extra")
    obj1 = SameTableChild.objects.get(id=obj.id)
    obj2 = FooModel.objects.get(id=obj.id)
    assert obj1.pk == obj2.pk
    obj2.name = "test2"
    obj2.save()
    obj1.refresh_from_db()
    assert obj1.name == obj2.name
    assert obj.extended == "extra"


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_same_collection_one_to_one():
    FooModel.objects.all().delete()
    obj1 = FooModel.objects.create(name="test", json_field={"foo": "bar"})
    obj1.extends = SameTableOneToOne(extra="extra")
    obj1.extends.save()
    obj2 = FooModel.objects.get(id=obj1.id)
    assert obj2.pk == obj2.extends.pk
    assert obj2.extends.extra == "extra"


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_different_collection_one_to_one_select():
    FooModel.objects.all().delete()
    obj1 = FooModel.objects.create(name="test", json_field={"foo": "bar"})
    obj1.another_extends = DifferentTableOneToOne(extra="extra")
    obj1.another_extends.save()
    obj2 = FooModel.objects.get(id=obj1.id)
    assert obj2.another_extends.extra == "extra"
    with pytest.raises(NotImplementedError):
        obj3 = FooModel.objects.select_related("another_extends").get(id=obj1.id)
        assert obj3.another_extends.extra == "extra"


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_related_model():
    FooModel.objects.all().delete()
    RelatedModel.objects.all().delete()

    foo = FooModel.objects.create(name="test", json_field={"foo": "bar"})
    RelatedModel.objects.create(name="related", foo=foo)

    assert len(RelatedModel.objects.filter(foo=foo).all()) == 1
    assert len(RelatedModel.objects.exclude(foo=foo).all()) == 0
    assert len(RelatedModel.objects.filter(foo=ObjectId()).all()) == 0
    assert len(RelatedModel.objects.exclude(foo=ObjectId()).all()) == 1

    foo.related.all().delete()
    assert len(foo.related.all()) == 0


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_related_model_prefetch():
    FooModel.objects.all().delete()
    RelatedModel.objects.all().delete()

    foo = FooModel.objects.create(name="test", json_field={"foo": "bar"})
    RelatedModel.objects.create(name="related", foo=foo)

    foo = FooModel.objects.prefetch_related("related").get(name="test")
    assert len(foo.related.all()) == 1


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_aggregation_count():
    FooModel.objects.all().delete()
    assert not FooModel.objects.all().exists()
    assert FooModel.objects.count() == 0
    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    assert FooModel.objects.filter(name="test").count() == 1
    assert FooModel.objects.exclude(name="test").count() == 0


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_ordering():
    FooModel.objects.all().delete()
    FooModel.objects.create(name="1", json_field={"foo": "bar"})
    FooModel.objects.create(name="2", json_field={"foo": "bar"})

    assert list(FooModel.objects.all().order_by("name"))[0].name == "1"
    assert list(FooModel.objects.all().order_by("-name"))[0].name == "2"


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_prohibit_nested_queries():
    # TODO: convert nested queries to aggregations
    FooModel.objects.all().delete()
    RelatedModel.objects.all().delete()

    FooModel.objects.create(name="1", json_field={"foo": "bar"})
    RelatedModel.objects.create(name="related", foo=FooModel.objects.get(name="1"))

    with pytest.raises(NotImplementedError):
        FooModel.objects.filter(related__name="related").delete()


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_distinct():
    FooModel.objects.all().delete()
    FooModel.objects.create(name="1", json_field={"foo": "bar"}, date_field=datetime.date.today())
    FooModel.objects.create(name="2", json_field={"foo": "bar"}, date_field=datetime.date.today())
    assert list(FooModel.objects.order_by("name").distinct().values_list("name", flat=True)) == [
        "1",
        "2",
    ]
    assert list(FooModel.objects.order_by("name").distinct().values_list("name", "date_field")) == [
        ("1", datetime.date.today()),
        ("2", datetime.date.today()),
    ]


@pytest.mark.django_db(databases=["mongodb"])
def test_prefer_search_qs():
    qs = FooModel.objects.all().prefer_search()
    assert qs._prefer_search is True
    qs = qs.filter(name="test")
    assert qs._prefer_search is True


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="CI does not have mongodb search")
@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_search_index(search_index):
    FooModel.objects.all().delete()
    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    FooModel.objects.create(name="test1", json_field={"foo": "bar"})
    # search index needs to sync
    time.sleep(1)
    # regular search term
    search_qs = FooModel.objects.annotate(search=SearchVector("name")).filter(
        search=SearchQuery("test")
    )
    assert len(list(search_qs)) == 1
    # wildcard search term
    search_qs = FooModel.objects.annotate(search=SearchVector("name", "name2")).filter(
        search=SearchQuery("test*")
    )
    assert len(list(search_qs)) == 2

    prefer_search_qs = FooModel.objects.all().prefer_search().filter(name="test")
    assert len(list(prefer_search_qs)) == 1

    with pytest.raises(RequiresSearchIndex):
        search_qs = FooModel.objects.annotate(search=SearchVector("datetime_field")).filter(
            search=SearchQuery("test")
        )
        assert len(list(search_qs)) == 0


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_raw_query():
    FooModel.objects.all().delete()
    FooModel.objects.create(name="1", json_field={"foo": "bar"}, date_field=datetime.date.today())
    FooModel.objects.create(name="2", json_field={"foo": "bar"}, date_field=datetime.date.today())

    FooModel.objects.filter(RawMongoDBQuery({"name": "1"})).delete()
    assert len(FooModel.objects.all()) == 1


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_stages():
    FooModel.objects.all().delete()
    FooModel.objects.create(name="1", json_field={"foo": "bar"}, date_field=datetime.date.today())
    FooModel.objects.create(name="2", json_field={"foo": "bar"}, date_field=datetime.date.today())
    assert FooModel.objects.all().add_aggregation_stage({"$match": {"name": "1"}}).count() == 1
    FooModel.objects.all().add_aggregation_stage({"$match": {"name": "1"}}).delete()
    assert len(FooModel.objects.all()) == 1
    FooModel.objects.all().add_aggregation_stage({"$match": {"name": {"$in": ["1", "2"]}}}).delete()
    assert len(FooModel.objects.all()) == 0


@pytest.mark.django_db(databases=["mongodb", "default"])
def test_reference_model():
    RefModel.objects.create(name="foo", json={"foo": "bar"})
    assert len(RefModel.objects.all()) == 1
    assert len(RefModel.objects.filter(name="foo").all()) == 1
    RefModel.objects.filter(name="foo").delete()


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_basic():
    """Test basic decimal field CRUD operations with BSON Decimal128."""
    # Test create with default value
    obj = DecimalFieldModel.objects.create()
    assert obj.value == Decimal("0")

    # Test create with specific value
    test_value = Decimal("123.45")
    obj2 = DecimalFieldModel.objects.create(value=test_value)
    obj2.refresh_from_db()
    assert obj2.value == test_value
    assert isinstance(obj2.value, Decimal)


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_precision():
    """Test decimal field precision preservation."""
    # Test various precision values
    test_cases = [
        Decimal("0.01"),
        Decimal("99999999.99"),  # Max for 10 digits, 2 decimal places
        Decimal("-123.45"),
        Decimal("0.00"),
        Decimal("1234567.89"),
    ]

    for test_value in test_cases:
        obj = DecimalFieldModel.objects.create(value=test_value)
        obj.refresh_from_db()
        assert obj.value == test_value


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_string_conversion():
    """Test storing and retrieving string decimals."""
    # Create object with string value
    obj = DecimalFieldModel.objects.create(value="456.78")
    obj.refresh_from_db()
    assert obj.value == Decimal("456.78")
    assert isinstance(obj.value, Decimal)


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_none_handling():
    """Test None/null handling in decimal fields."""

    # Create a model with nullable decimal field for proper None testing
    class NullableDecimalModel(models.Model):
        value = models.DecimalField(null=True, blank=True, decimal_places=2, max_digits=10)

        class Meta:
            app_label = "testapp"
            db_table = "testapp_nullabledecimalmodel"

    # Create object with None value
    obj = NullableDecimalModel.objects.create(value=None)
    obj.refresh_from_db()
    assert obj.value is None

    # Update None to a decimal value
    obj.value = Decimal("123.45")
    obj.save()
    obj.refresh_from_db()
    assert obj.value == Decimal("123.45")


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_filtering():
    """Test filtering operations on decimal fields."""
    DecimalFieldModel.objects.all().delete()

    # Create test data
    values = [Decimal("10.50"), Decimal("20.75"), Decimal("30.00"), Decimal("5.25")]
    for val in values:
        DecimalFieldModel.objects.create(value=val)

    # Test exact match
    assert DecimalFieldModel.objects.filter(value=Decimal("10.50")).count() == 1

    # Test greater than
    assert DecimalFieldModel.objects.filter(value__gt=Decimal("20")).count() == 2

    # Test less than or equal
    assert DecimalFieldModel.objects.filter(value__lte=Decimal("20.75")).count() == 3

    # Test range
    assert (
        DecimalFieldModel.objects.filter(value__gte=Decimal("10"), value__lte=Decimal("25")).count()
        == 2
    )


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_ordering():
    """Test ordering by decimal fields."""
    DecimalFieldModel.objects.all().delete()

    values = [Decimal("30.00"), Decimal("10.50"), Decimal("20.75"), Decimal("5.25")]
    for val in values:
        DecimalFieldModel.objects.create(value=val)

    # Test ascending order
    ordered = list(DecimalFieldModel.objects.order_by("value").values_list("value", flat=True))
    assert ordered == [Decimal("5.25"), Decimal("10.50"), Decimal("20.75"), Decimal("30.00")]

    # Test descending order
    ordered_desc = list(
        DecimalFieldModel.objects.order_by("-value").values_list("value", flat=True)
    )
    assert ordered_desc == [Decimal("30.00"), Decimal("20.75"), Decimal("10.50"), Decimal("5.25")]


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_update():
    """Test updating decimal fields."""
    obj = DecimalFieldModel.objects.create(value=Decimal("100.00"))

    # Update via save
    obj.value = Decimal("200.50")
    obj.save()
    obj.refresh_from_db()
    assert obj.value == Decimal("200.50")

    # Update via queryset
    DecimalFieldModel.objects.filter(id=obj.id).update(value=Decimal("300.75"))
    obj.refresh_from_db()
    assert obj.value == Decimal("300.75")


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_edge_cases():
    """Test edge cases for decimal fields."""
    # Test zero
    obj = DecimalFieldModel.objects.create(value=Decimal("0"))
    obj.refresh_from_db()
    assert obj.value == Decimal("0")

    # Test negative zero (should be normalized to zero)
    obj2 = DecimalFieldModel.objects.create(value=Decimal("-0"))
    obj2.refresh_from_db()
    assert obj2.value == Decimal("0")

    # Test very small decimal
    obj3 = DecimalFieldModel.objects.create(value=Decimal("0.01"))
    obj3.refresh_from_db()
    assert obj3.value == Decimal("0.01")


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_aggregation():
    """Test aggregation operations on decimal fields."""
    DecimalFieldModel.objects.all().delete()

    # Create test data
    values = [Decimal("10.50"), Decimal("20.75"), Decimal("30.00")]
    for val in values:
        DecimalFieldModel.objects.create(value=val)

    # Test exists
    assert DecimalFieldModel.objects.filter(value__gt=Decimal("0")).exists()

    # Test count
    assert DecimalFieldModel.objects.filter(value__gte=Decimal("20")).count() == 2


@pytest.mark.django_db(databases=["mongodb"])
def test_decimal_field_backward_compatibility():
    """Test backward compatibility with legacy string decimal storage."""

    # Connect directly to MongoDB to insert string decimal values
    db_settings = settings.DATABASES["mongodb"]
    client = MongoClient(**db_settings["CLIENT"])
    db = client[db_settings["NAME"]]
    collection = db["testapp_decimalfieldmodel"]

    # Clean up
    collection.delete_many({})

    # Insert legacy string decimal values directly
    collection.insert_many(
        [
            {"value": "123.45"},  # String decimal
            {"value": Decimal128("678.90")},  # BSON Decimal128
            {"value": None},  # Null value
        ]
    )

    # Test that Django can read all formats correctly
    all_objects = list(DecimalFieldModel.objects.all())
    assert len(all_objects) == 3

    # Check that we can read all values correctly
    values = [obj.value for obj in all_objects]
    assert None in values
    assert Decimal("123.45") in values
    assert Decimal("678.90") in values

    # Test filtering works with null values
    assert DecimalFieldModel.objects.filter(value__isnull=True).count() == 1
    assert DecimalFieldModel.objects.filter(value__isnull=False).count() == 2

    # Update all values to ensure they're stored as BSON Decimal128
    for obj in DecimalFieldModel.objects.all():
        if obj.value is not None:
            obj.save()  # This will convert string to Decimal128

    # Now filtering should work correctly
    assert DecimalFieldModel.objects.filter(value__gt=Decimal("200")).count() == 1
    assert DecimalFieldModel.objects.filter(value__lt=Decimal("200")).count() == 1


@pytest.mark.django_db(databases=["mongodb"])
def test_in_lookup_field_conversion():
    """Test that __in lookups properly convert field values."""
    # Test with ObjectId fields (FooModel)
    item1 = FooModel.objects.create(name="test1", json_field={"foo": "bar"})
    item2 = FooModel.objects.create(name="test2", json_field={"foo": "baz"})

    # Test ObjectId __in lookup
    result = FooModel.objects.filter(id__in=[item1.id, item2.id])
    assert result.count() == 2

    # Test with string IDs
    result = FooModel.objects.filter(id__in=[str(item1.id), str(item2.id)])
    assert result.count() == 2

    # Test with DecimalField
    DecimalFieldModel.objects.all().delete()
    DecimalFieldModel.objects.create(value=Decimal("10.50"))
    DecimalFieldModel.objects.create(value=Decimal("20.75"))

    # Test Decimal __in lookup
    result = DecimalFieldModel.objects.filter(value__in=[Decimal("10.50"), Decimal("20.75")])
    assert result.count() == 2

    # Test with mixed types (should still work due to field conversion)
    result = DecimalFieldModel.objects.filter(value__in=[Decimal("10.50"), "20.75"])
    assert result.count() == 2
