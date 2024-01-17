import pytest
from django.db import connections
from pymongo.operations import SearchIndexModel


@pytest.fixture
def search_index():
    connections["default"].cursor().connection["testapp_foomodel"].create_search_index(
        SearchIndexModel(
            {
                "analyzer": "lucene.standard",
                "mappings": {
                    "fields": {
                        "name": [{"type": "string"}, {"type": "stringFacet"}],
                        "datetime_field": [{"type": "dateFacet"}, {"type": "date"}],
                    }
                },
            }
        )
    )
