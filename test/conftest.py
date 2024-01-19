import time

import pytest
from django.db import connections
from pymongo.operations import SearchIndexModel


@pytest.fixture()
def search_index():
    try:
        connections["mongodb"].cursor().connection["testapp_foomodel"].drop_search_index("default")
    except Exception:
        pass
    connections["mongodb"].cursor().connection["testapp_foomodel"].create_search_index(
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
                        }
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
        indexes = list(
            connections["mongodb"].cursor().connection["testapp_foomodel"].list_search_indexes()
        )
        if any(index["status"] == "READY" for index in indexes):
            break
        i += 1
        if i > 100:
            raise RuntimeError("Index not ready")
