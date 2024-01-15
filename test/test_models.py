import datetime

import pytest
from bson import ObjectId

from refapp.models import RefModel
from testapp.models import (
    DifferentTableOneToOne,
    FooModel,
    RelatedModel,
    SameTableChild,
    SameTableOneToOne,
)


@pytest.mark.django_db
def test_mongo_model():
    now = datetime.datetime.now().replace(microsecond=0)
    item = FooModel.objects.create(
        name="test",
        json_field={"foo": "bar"},
    )
    FooModel.objects.filter(name="test").update(
        datetime_field=now, date_field=now.date(), time_field=now.time()
    )
    item.refresh_from_db()
    assert item.json_field == {"foo": "bar"}
    assert item.name == "test"
    assert isinstance(item.datetime_field, datetime.datetime)
    assert item.datetime_field == now
    assert item.date_field == now.date()
    assert item.time_field == now.time()


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_mongo_model_values():
    FooModel.objects.all().delete()
    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    item_values = list(FooModel.objects.values("name"))
    assert item_values[0]["name"] == "test"


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_mongo_same_collection_one_to_one():
    FooModel.objects.all().delete()
    obj1 = FooModel.objects.create(name="test", json_field={"foo": "bar"})
    obj1.extends = SameTableOneToOne(extra="extra")
    obj1.extends.save()
    obj2 = FooModel.objects.get(id=obj1.id)
    assert obj2.pk == obj2.extends.pk
    assert obj2.extends.extra == "extra"


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_mongo_related_model_prefetch():
    FooModel.objects.all().delete()
    RelatedModel.objects.all().delete()

    foo = FooModel.objects.create(name="test", json_field={"foo": "bar"})
    RelatedModel.objects.create(name="related", foo=foo)

    foo = FooModel.objects.prefetch_related("related").get(name="test")
    assert len(foo.related.all()) == 1


@pytest.mark.django_db
def test_mongo_aggregation_count():
    FooModel.objects.all().delete()
    assert not FooModel.objects.all().exists()
    assert FooModel.objects.count() == 0


@pytest.mark.django_db
def test_mongo_ordering():
    FooModel.objects.all().delete()
    FooModel.objects.create(name="1", json_field={"foo": "bar"})
    FooModel.objects.create(name="2", json_field={"foo": "bar"})

    assert list(FooModel.objects.all().order_by("name"))[0].name == "1"
    assert list(FooModel.objects.all().order_by("-name"))[0].name == "2"


@pytest.mark.django_db
def test_prefer_search():
    FooModel.objects.all().delete()
    assert list(FooModel.objects.all().prefer_search(True)) == []


@pytest.mark.django_db
def test_reference_model():
    RefModel.objects.create(name="foo", json={"foo": "bar"})
    assert len(RefModel.objects.all()) == 1
    assert len(RefModel.objects.filter(name="foo").all()) == 1
    RefModel.objects.filter(name="foo").delete()
