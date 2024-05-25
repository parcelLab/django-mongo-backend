import datetime
import os
import time
from datetime import timedelta

import pytest
from bson import ObjectId
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.utils.timezone import now

from django_mongodb.expressions import RawMongoDBQuery
from django_mongodb.query import RequiresSearchIndex
from refapp.models import RefModel
from testapp.models import (
    DifferentTableOneToOne,
    FooModel,
    RelatedModel,
    SameTableChild,
    SameTableOneToOne,
)


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_model():
    now = datetime.datetime.now().replace(microsecond=0)
    item = FooModel.objects.create(
        name="test",
        json_field={"foo": "bar"},
    )
    assert item.id is not None
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


@pytest.mark.django_db(databases=["mongodb"])
def test_db_prep():
    FooModel.objects.all().delete()
    item = FooModel.objects.create(
        name="test",
        json_field={"foo": "bar"},
    )
    assert len(FooModel.objects.filter(id=str(item.id)).all()) == 1


@pytest.mark.django_db(databases=["mongodb"])
def test_manager_methods():
    FooModel.objects.all().delete()
    item1 = FooModel.objects.get_or_create(name="test", defaults={"json_field": {"foo": "bar"}})
    item2 = FooModel.objects.get_or_create(name="test", defaults={"json_field": {"foo": "bar"}})
    assert item1[0] is not None
    assert item1[0].id == item2[0].id


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_emtpy():
    FooModel.objects.all().delete()
    assert len(list(FooModel.objects.none())) == 0


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_lookup():
    FooModel.objects.all().delete()

    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    FooModel.objects.create(name="test2", json_field={"foo": "bar"})

    assert len(list(FooModel.objects.filter(datetime_field__gt=now() - timedelta(hours=1)))) == 2
    assert len(list(FooModel.objects.filter(name="test"))) == 1


@pytest.mark.django_db(databases=["mongodb"])
def test_mongo_int_isnull():
    FooModel.objects.all().delete()

    FooModel.objects.create(name="test", json_field={"foo": "bar"})
    assert len(list(FooModel.objects.filter(int_field__isnull=True))) == 0
    assert len(list(FooModel.objects.filter(name2__isnull=True))) == 1

    assert len(list(FooModel.objects.exclude(int_field__isnull=True))) == 1
    assert len(list(FooModel.objects.exclude(name2__isnull=True))) == 0


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


@pytest.mark.django_db(databases=["default"])
def test_reference_model():
    RefModel.objects.create(name="foo", json={"foo": "bar"})
    assert len(RefModel.objects.all()) == 1
    assert len(RefModel.objects.filter(name="foo").all()) == 1
    RefModel.objects.filter(name="foo").delete()
