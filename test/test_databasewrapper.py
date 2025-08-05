import pytest
from django.db import connections
from pymongo.collection import Collection
from pymongo.database import Database


@pytest.mark.django_db(databases=["mongodb"])
def test_raw_connection():
    # To access collections, use the database connection directly
    connection = connections["mongodb"]
    assert connection.database is not None
    assert isinstance(connection.database, Database)
    assert isinstance(connection.database["foo"], Collection)
