from typing import TypeVar

from django.db import models


class MongoQuerySet(models.QuerySet):
    """QuerySet which uses MongoDB as backend"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prefer_search = False

    def prefer_search(self, prefer_search=True):
        obj = self._chain()
        obj._prefer_search = prefer_search
        obj.query.prefer_search = prefer_search
        return obj

    def _chain(self):
        """
        Add the _prefer_search hint to the chained query
        """
        obj = super()._chain()
        if obj._prefer_search:
            obj.query.prefer_search = obj._prefer_search
        return obj

    def _clone(self):
        obj = super()._clone()
        obj._prefer_search = self._prefer_search
        return obj


T = TypeVar("T")


class MongoManager(models.Manager[T]):
    """Manager which uses MongoDB as backend"""

    def get_queryset(self):
        return MongoQuerySet(self.model, using=self._db)

    def prefer_search(self, require_search=True):
        return self.get_queryset().prefer_search(require_search)
