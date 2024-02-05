import pytest
from django.db import connections
from pymongo.collection import Collection
from pymongo.database import Database


@pytest.mark.django_db(databases=["mongodb"])
def test_cursor():
    with connections["mongodb"].cursor() as cursor:
        assert isinstance(cursor.collections, Database)
        assert isinstance(cursor.collections["foo"], Collection)
