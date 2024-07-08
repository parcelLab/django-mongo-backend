from typing import Generic, Literal, TypeVar

from django.db import models

T = TypeVar("T")


class MongoQuerySet(Generic[T], models.QuerySet[T]):
    """QuerySet which uses MongoDB as backend"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prefer_search = False
        self._aggregation_stages = []

    def prefer_search(self, prefer_search=True):
        obj = self._chain()
        obj._prefer_search = prefer_search
        obj.query.prefer_search = prefer_search
        return obj

    def add_aggregation_stage(
        self,
        stage: dict,
        position: Literal["prepend", "pre-sort", "append"] = "prepend",
    ):
        obj = self._chain()
        obj._aggregation_stages.append((position, stage))
        obj.query.aggregation_stages = obj._aggregation_stages
        return obj

    def _chain(self):
        """
        Add the _prefer_search hint to the chained query
        """
        obj = super()._chain()
        if obj._prefer_search:
            obj.query.prefer_search = obj._prefer_search
        if obj._aggregation_stages:
            obj.query.aggregation_stages = obj._aggregation_stages
        return obj

    def _clone(self):
        obj = super()._clone()
        obj._prefer_search = self._prefer_search
        obj._aggregation_stages = self._aggregation_stages
        return obj


class MongoManager(Generic[T], models.Manager[T]):
    """Manager which uses MongoDB as backend"""

    def get_queryset(self) -> MongoQuerySet[T]:
        return MongoQuerySet(self.model, using=self._db)

    def prefer_search(self, require_search=True) -> MongoQuerySet[T]:
        return self.get_queryset().prefer_search(require_search)
