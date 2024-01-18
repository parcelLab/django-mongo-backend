import abc
from abc import ABC
from collections import OrderedDict

from django.contrib.postgres.search import SearchQuery, SearchVector, SearchVectorExact
from django.db.models import Count, sql
from django.db.models.expressions import BaseExpression, Col, Expression, Value
from django.db.models.fields.related_lookups import RelatedIn
from django.db.models.lookups import Exact, GreaterThanOrEqual, In, LessThanOrEqual
from django.db.models.sql import Query
from django.db.models.sql.where import WhereNode

from django_mongodb import models


class RequiresSearchException(Exception):
    pass


class Node(ABC):
    """MongoDB Query Node"""

    def __init__(self, node: Expression, mongo_meta):
        self.node = node
        self.mongo_meta = mongo_meta
        if hasattr(self.node, "rhs") and isinstance(self.node.rhs, BaseExpression):
            raise NotImplementedError(f"Subquery Expression not implemented: {str(self.node.rhs)}")

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
        super().__init__(exact, mongo_meta)
        self.lhs = exact.lhs
        self.rhs = exact.rhs
        self.mongo_meta = mongo_meta

    def get_mongo_query(self, is_search=False) -> dict:
        if self.lhs.target.attname in self.mongo_meta["search_fields"] and is_search:
            return {}
        lhs = self.lhs.target
        rhs = self.node.rhs
        if is_search and self.mongo_meta["search_fields"].get(lhs.attname):
            return {}
        if isinstance(lhs, models.ObjectIdField) and isinstance(self.rhs, str):
            rhs = models.ObjectIdField().to_python(rhs)
        return {lhs.column: {"$eq": rhs}}

    def get_search_types(self, attname):
        if attname in self.mongo_meta["search_fields"]:
            if "string" in self.mongo_meta["search_fields"][attname]:
                return "text", "query"
            else:
                return "equals", "value"

    def get_mongo_search(self) -> dict:
        if self.lhs.target.attname not in self.mongo_meta["search_fields"]:
            return {}
        query, value = self.get_search_types(self.lhs.target.attname)
        return {
            query: {
                "path": self.lhs.target.column,
                value: self.node.rhs,
            }
        }


class SearchNode(Node):
    """MongoDB Search Query Base Node"""

    def __init__(self, node: Expression, mongo_meta):
        self.node = node
        self.mongo_meta = mongo_meta

    def requires_search(self) -> bool:
        return True

    def get_mongo_query(self, **kwargs) -> dict:
        raise RequiresSearchException("SearchVectorExact requires application via search query.")


class MongoSearchVectorExact(SearchNode):
    """MongoDB Search Query Node for SearchVectorExact"""

    def __init__(self, exact: SearchVectorExact, mongo_meta):
        super().__init__(exact, mongo_meta)
        self.lhs: SearchVector = exact.lhs
        self.rhs: SearchQuery = exact.rhs

    def get_mongo_search(self) -> dict:
        rhs_expressions = self.lhs.get_source_expressions()
        lhs_expressions = self.rhs.get_source_expressions()
        columns = [expression.field.column for expression in rhs_expressions]
        query = [expression.value for expression in lhs_expressions]
        # weight = lhs.weight
        # config = lhs.config
        search_query = {"wildcard": {"path": columns, "query": query}}
        return search_query


class MongoIn(Node):
    """MongoDB Query Node for RelatedIn"""

    def __init__(self, related_in: RelatedIn, mongo_meta):
        super().__init__(related_in, mongo_meta)
        self.lhs = related_in.lhs
        self.rhs = related_in.rhs
        self.mongo_meta = mongo_meta

    def get_mongo_query(self, is_search=False) -> dict:
        if self.lhs.target.attname in self.mongo_meta["search_fields"] and is_search:
            return {}
        lhs = self.lhs.target
        rhs = self.rhs
        if is_search and self.mongo_meta["search_fields"].get(lhs.attname):
            return {}
        if isinstance(lhs, models.ObjectIdField) and isinstance(self.rhs, str):
            rhs = models.ObjectIdField().to_python(rhs)
        return {lhs.column: {"$in": rhs}}

    def get_mongo_search(self) -> dict:
        if self.lhs.target.attname not in self.mongo_meta["search_fields"]:
            return {}
        return {
            "in": {
                "path": self.lhs.target.column,
                "value": self.rhs,
            }
        }


class MongoRelatedIn(MongoIn):
    pass


class MongoEqualityComparison(Node, ABC):
    """MongoDB Query Node for LessThanOrEqual"""

    operator: str

    def __init__(self, operator: LessThanOrEqual | GreaterThanOrEqual, mongo_meta):
        super().__init__(operator, mongo_meta)
        self.lhs = operator.lhs
        self.rhs = operator.rhs
        self.operator = {
            LessThanOrEqual: "lte",
            GreaterThanOrEqual: "gte",
        }[type(operator)]
        self.mongo_meta = mongo_meta

    def get_mongo_query(self, is_search=False) -> dict:
        if self.lhs.target.attname in self.mongo_meta["search_fields"] and is_search:
            return {}
        lhs = self.lhs.target
        rhs = self.rhs
        if is_search and self.mongo_meta["search_fields"].get(lhs.attname):
            return {}
        if isinstance(lhs, models.ObjectIdField) and isinstance(self.rhs, str):
            rhs = models.ObjectIdField().to_python(rhs)
        return {lhs.column: {f"${self.operator}": rhs}}

    def get_mongo_search(self) -> dict:
        if self.lhs.target.attname not in self.mongo_meta["search_fields"]:
            return {}
        return {
            "range": {
                "path": self.lhs.target.column,
                self.operator: self.rhs,
            }
        }


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
                self.children.append(MongoSearchVectorExact(child, self.mongo_meta))
            elif isinstance(child, RelatedIn):
                self.children.append(MongoRelatedIn(child, self.mongo_meta))
            elif isinstance(child, In):
                self.children.append(MongoIn(child, self.mongo_meta))
            elif isinstance(child, WhereNode):
                self.children.append(MongoWhereNode(child, self.mongo_meta))
            elif isinstance(child, (LessThanOrEqual, GreaterThanOrEqual)):
                self.children.append(MongoEqualityComparison(child, self.mongo_meta))
            else:
                raise NotImplementedError(f"Node not implemented: {type(child)}")

    def __bool__(self):
        return len(self.children) > 0

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
        child_queries = list(filter(bool, [child.get_mongo_search() for child in self.children]))
        if len(child_queries) == 0:
            return {}
        elif self.connector == "AND":
            return {"compound": {"must": child_queries}}
        elif self.connector == "OR":
            return {"compound": {"should": child_queries}}
        else:
            raise Exception(f"Unsupported connector: {self.connector}")


class MongoColSelect:
    def __init__(self, col: Col, alias: str | None, mongo_meta):
        self.col = col
        self.mongo_meta = mongo_meta
        self.alias = alias

    def get_mongo(self):
        return {"$project": {(self.alias or self.col.target.attname): f"${self.col.target.column}"}}


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
        for col in _cols:
            [column, _, alias] = col
            match column:
                case Col():
                    self.cols.append(MongoColSelect(column, alias, mongo_meta))
                case Value():
                    self.cols.append(MongoValueSelect(column, alias, mongo_meta))
                case Count():
                    self.cols.append(MongoCountSelect(column, alias, mongo_meta))
                case SearchVector():
                    pass  # ignoring search vector in results
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
        self.query = query
        self.order = query.order_by

    def get_mongo_order(self, attname_as_key=False):
        key = "attname" if attname_as_key else "column"
        mongo_order = {}
        meta = self.query.get_meta()
        fields = {field.name: field for field in self.query.model._meta.get_fields()}
        for field in self.order or []:
            if field.startswith("-"):
                ordering = -1
                field = field[1:]
            else:
                ordering = 1
            field = meta.pk.attname if field == "pk" else field
            mongo_order.update({getattr(fields[field], key): ordering})
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
