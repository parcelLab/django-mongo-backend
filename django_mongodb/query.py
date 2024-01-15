import abc
from abc import ABC
from collections import defaultdict, OrderedDict

from django.contrib.postgres.search import SearchVectorExact, SearchQuery, SearchVector
from django.db.models import sql, Count
from django.db.models.expressions import Col, Expression, Value
from django.db.models.fields.related_lookups import RelatedIn
from django.db.models.lookups import Exact, In
from django.db.models.sql import Query
from django.db.models.sql.where import WhereNode

from django_mongodb import models


class RequiresSearchException(Exception):
    pass


class Node(ABC):
    """MongoDB Query Node"""

    def requires_search(self) -> bool:
        return False

    @abc.abstractmethod
    def get_mongo_query(self, is_search=...) -> dict:
        ...

    @abc.abstractmethod
    def get_mongo_search(self) -> dict:
        ...


class MongoExact(Node):
    """MongoDB Query Node for Exact"""

    def __init__(self, exact: Exact, mongo_meta):
        self.node = exact
        self.lhs = exact.lhs
        self.rhs = exact.rhs
        self.mongo_meta = mongo_meta

    def get_mongo_query(self, is_search=False) -> dict:
        lhs = self.lhs.target
        rhs = self.node.rhs
        if is_search and self.mongo_meta["search_fields"].get(lhs.attname):
            return {}
        if isinstance(lhs, models.ObjectIdField) and isinstance(self.rhs, str):
            rhs = models.ObjectIdField().to_python(rhs)
        return {lhs.column: {"$eq": rhs}}

    def get_mongo_search(self) -> dict:
        return {
            "equals": {
                "path": self.lhs.target.column,
                "value": self.node.rhs,
            }
        }


class SearchNode(Node):
    """MongoDB Search Query Base Node"""

    def requires_search(self) -> bool:
        return True

    def get_mongo_query(self, **kwargs) -> dict:
        raise RequiresSearchException("SearchVectorExact requires application via search query.")


class MongoSearchVectorExact(SearchNode):
    """MongoDB Search Query Node for SearchVectorExact"""

    def __init__(self, exact: SearchVectorExact):
        self.node = exact
        self.lhs: SearchVector = exact.lhs
        self.rhs: SearchQuery = exact.rhs

    def get_mongo_search(self) -> dict:
        rhs_expressions = self.lhs.get_source_expressions()
        lhs_expressions = self.rhs.get_source_expressions()
        columns = [expression.field.column for expression in rhs_expressions]
        query = [expression.value for expression in lhs_expressions]
        # weigh<t = lhs.weight
        # config = lhs.config
        search_query = {"text": {"path": columns, "query": query}}
        return search_query


class MongoIn(Node):
    """MongoDB Query Node for RelatedIn"""

    def __init__(self, related_in: RelatedIn, mongo_meta):
        self.node = related_in
        self.lhs = related_in.lhs
        self.rhs = related_in.rhs
        self.mongo_meta = mongo_meta

    def get_mongo_query(self, is_search=False) -> dict:
        lhs = self.lhs.target
        rhs = self.rhs
        if is_search and self.mongo_meta["search_fields"].get(lhs.attname):
            return {}
        if isinstance(lhs, models.ObjectIdField) and isinstance(self.rhs, str):
            rhs = models.ObjectIdField().to_python(rhs)
        return {lhs.column: {"$in": rhs}}

    def get_mongo_search(self) -> dict:
        return {
            "in": {
                "path": self.lhs.target.column,
                "value": self.rhs,
            }
        }


class MongoRelatedIn(MongoIn):
    pass


class MongoWhereNode(Node):
    """MongoDB Query Node for WhereNode"""

    def __init__(self, where: WhereNode, mongo_meta):
        self.node = where
        self.connector = where.connector
        self.children: list[Node] = []
        self.mongo_meta = mongo_meta
        self.negated = where.negated
        for child in self.node.children:
            if isinstance(child, Exact):
                self.children.append(MongoExact(child, self.mongo_meta))
            elif isinstance(child, SearchVectorExact):
                self.children.append(MongoSearchVectorExact(child))
            elif isinstance(child, RelatedIn):
                self.children.append(MongoRelatedIn(child, self.mongo_meta))
            elif isinstance(child, In):
                self.children.append(MongoIn(child, self.mongo_meta))
            elif isinstance(child, WhereNode):
                self.children.append(MongoWhereNode(child, self.mongo_meta))
            else:
                raise NotImplementedError(f"Node not implemented: {type(child)}")

    def requires_search(self) -> bool:
        return any(child.requires_search() for child in self.children)

    def get_mongo_query(self, is_search=False) -> dict:
        child_queries = list(
            filter(
                bool,
                [child.get_mongo_query(is_search=is_search) for child in self.children],
            )
        )
        if len(child_queries) == 0:
            return {}
        if self.connector == "AND":
            return {"$and": child_queries} if not self.negated else {"$nor": child_queries}
        elif self.connector == "OR":
            return {"$or": child_queries} if not self.negated else {"$nor": child_queries}
        else:
            raise Exception(f"Unsupported connector: {self.connector}")

    def get_mongo_search(self) -> dict:
        if len(self.children) == 0:
            return {}
        if self.connector == "AND":
            return {"compound": {"must": [child.get_mongo_search() for child in self.children]}}
        elif self.connector == "OR":
            return {"compound": {"should": [child.get_mongo_search() for child in self.children]}}
        else:
            raise Exception(f"Unsupported connector: {self.connector}")


class MongoColSelect:
    def __init__(self, col: Col, alias: str | None, mongo_meta):
        self.col = col
        self.mongo_meta = mongo_meta
        self.alias = alias

    def get_mongo(self):
        return {
            "$project": {
                (self.alias or self.col.target.attname): {
                    "$ifNull": [f"${self.col.target.column}", "null"]
                }
            }
        }


class MongoValueSelect:
    def __init__(self, col: Value, alias: str | None, mongo_meta):
        self.col = col
        self.mongo_meta = mongo_meta
        self.alias = alias

    def get_mongo(self):
        return {"$project": {(self.alias): self.col.value}}


class MongoCountSelect:
    def __init__(self, col: Value, alias: str | None, mongo_meta):
        self.col = col
        self.mongo_meta = mongo_meta
        self.alias = alias

    def get_mongo(self):
        return {
            "$group": {"_id": None, "_count": {"$sum": 1}},
            "$project": {"_id": None, (self.alias or self.col.output_field.column): "$_count"},
        }


class MongoSelect:
    def __init__(self, _cols: list[tuple[Expression, tuple, str | None]], mongo_meta):
        self.mongo_meta = mongo_meta
        self.cols = []
        models = set()
        for col in _cols:
            [column, _, alias] = col
            match column:
                case Col():
                    models.add(column.output_field.model)
                    self.cols.append(MongoColSelect(column, alias, mongo_meta))
                case Value():
                    self.cols.append(MongoValueSelect(column, alias, mongo_meta))
                case Count():
                    self.cols.append(MongoCountSelect(column, alias, mongo_meta))
                case _:
                    raise NotImplementedError(f"Select expression not implemented: {col}")

    def get_mongo(self):
        pipeline_dict: dict[str, dict] = OrderedDict()
        pipeline_dict["$group"] = dict()
        pipeline_dict["$project"] = dict()
        for col in self.cols:
            mongo_query = col.get_mongo()
            for key, item in mongo_query.items():
                pipeline_dict[key].update(item)

        return [{key: item} for key, item in pipeline_dict.items() if item]


class MongoOrdering:
    """MongoDB Query Node for Ordering"""

    def __init__(self, query: Query):
        self.order = query.order_by

    def get_mongo_order(self):
        mongo_order = {}
        for field in self.order or []:
            if field.startswith("-"):
                ordering = -1
                field = field[1:]
            else:
                ordering = 1
            field = "_id" if field == "pk" else field
            mongo_order.update({field: ordering})
        return mongo_order


class MongoQuery(sql.Query):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefer_search = False

    def clone(self, *args):
        obj = super().clone()
        obj.prefer_search = self.prefer_search
        return obj


class MongoCompiler:
    """MongoDB Query Compiler based on Django Query"""

    def get_mongo_query(self):
        return self.where.get_mongo_query()

    def _get_search_pipeline(self) -> tuple[list[dict], dict]:
        pipeline, project_meta = [], {}
        pipeline.append({"$search": self.where.get_mongo_search()})
        if match := self.where.get_mongo_query(is_search=True):
            pipeline.append({"$match": match})
        project_meta.update({"meta": "$$SEARCH_META"})
        return pipeline, project_meta

    def get_count(self):
        pipeline = []
        is_search = self.where.requires_search()
        if self.require_search or is_search:
            pipeline.append({"$searchMeta": self.where.get_mongo_search()})
        else:
            pipeline.append({"$match": self.where.get_mongo_query()})
            pipeline.append({"$count": "count"})
        return pipeline
