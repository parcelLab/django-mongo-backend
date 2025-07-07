import time

import pytest
from django.db import connections
from pymongo.operations import SearchIndexModel

from testapp.models import FooModel


@pytest.fixture(autouse=True)
def clean_db():
    FooModel.objects.all().delete()


@pytest.fixture()
def search_index():
    # Ensure the collection exists by creating a dummy document and then deleting it
    collection = connections["mongodb"].cursor().connection["testapp_foomodel"]
    collection.insert_one({"_id": "dummy"})
    collection.delete_one({"_id": "dummy"})

    try:
        collection.drop_search_index("default")
    except Exception:
        pass
    collection.create_search_index(
        SearchIndexModel(
            {
                "analyzer": "lucene.standard",
                "mappings": {
                    "dynamic": True,
                    "fields": {
                        "name": {
                            "analyzer": "lucene.keyword",
                            "norms": "omit",
                            "searchAnalyzer": "lucene.keyword",
                            "store": False,
                            "type": "string",
                        },
                        "name_2": {
                            "analyzer": "lucene.keyword",
                            "norms": "omit",
                            "searchAnalyzer": "lucene.keyword",
                            "store": False,
                            "type": "string",
                        },
                    },
                },
            },
            name="default",
        )
    )
    i = 0
    # we need to wait until the index is ready
    while True:
        time.sleep(1.0)
        indexes = list(collection.list_search_indexes())
        if any(index["status"] == "READY" for index in indexes):
            break
        i += 1
        if i > 100:
            raise RuntimeError("Index not ready")
