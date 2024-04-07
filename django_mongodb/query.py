import abc
from abc import ABC, abstractmethod
from collections import OrderedDict

from django.contrib.postgres.search import SearchQuery, SearchVector, SearchVectorExact
from django.db.models import Count
from django.db.models.expressions import BaseExpression, Col, Expression, Value
from django.db.models.fields.related_lookups import RelatedExact, RelatedIn
from django.db.models.lookups import (
    Exact,
    GreaterThan,
    GreaterThanOrEqual,
    In,
    IntegerFieldExact,
    LessThan,
    LessThanOrEqual,
    Lookup,
)
from django.db.models.sql import Query
from django.db.models.sql.where import NothingNode, WhereNode

from django_mongodb.expressions import RawMongoDBQuery


class RequiresSearchException(Exception):
    pass


class RequiresSearchIndex(Exception):
    pass


class Node(ABC):
    def __init__(self, node: Expression, mongo_meta):
        self.node = node
        self.mongo_meta = mongo_meta

    def requires_search(self) -> bool:
        return False

    @abc.abstractmethod
    def get_mongo_query(self, compiler, connection, requires_search=...) -> dict: ...

    @abc.abstractmethod
    def get_mongo_search(self, compiler, connection) -> dict: ...


class RawMongoQueryExpression(Node):
    def __init__(self, node: RawMongoDBQuery, mongo_meta):
        super().__init__(node, mongo_meta)
        self.node = node

    def get_mongo_query(self, compiler, connection, is_search=False) -> dict:
        return self.node.query

    def get_mongo_search(self, compiler, connection) -> dict:
        return {}


class MongoLookup(Node):
    """MongoDB Query Node"""

    filter_operator: str

    def __init__(self, node: Lookup, mongo_meta):
        super().__init__(node, mongo_meta)
        self.lhs = node.get_prep_lhs()
        self.rhs = node.get_prep_lookup()
        if hasattr(self.node, "rhs") and isinstance(self.node.rhs, BaseExpression):
            raise NotImplementedError(f"Subquery Expression not implemented: {str(self.node.rhs)}")

    def get_mongo_query(self, compiler, connection, is_search=False) -> dict:
        if self.lhs.target.attname in self.mongo_meta["search_fields"] and is_search:
            return {}
        else:
            return self._get_mongo_query(compiler, connection)

    def _get_mongo_query(self, compiler, connection, is_search=False) -> dict:
        if self.lhs.target.attname in self.mongo_meta["search_fields"] and is_search:
            return {}
        lhs = self.lhs.target
        rhs = self.rhs
        if is_search and self.mongo_meta["search_fields"].get(lhs.attname):
            return {}
        return {lhs.column: {self.filter_operator: rhs}}

    def get_mongo_search(self, compiler, connection) -> dict:
        if self.lhs.target.attname not in self.mongo_meta["search_fields"]:
            return {}
        if not self.rhs:
            return {}
        else:
            return self._get_mongo_search(compiler, connection)

    @abc.abstractmethod
    def _get_mongo_search(self, compiler, connection) -> dict: ...


class MongoExact(MongoLookup):
    """MongoDB Query Node for Exact"""

    filter_operator = "$eq"

    def get_search_types(self, attname):
        if attname in self.mongo_meta["search_fields"]:
            if "string" in self.mongo_meta["search_fields"][attname]:
                return "text", "query"
            else:
                return "equals", "value"

    def _get_mongo_search(self, compiler, connection) -> dict:
        if self.lhs.target.attname not in self.mongo_meta["search_fields"]:
            return {}
        query, value = self.get_search_types(self.lhs.target.attname)
        return {
            query: {
                "path": self.lhs.target.column,
                value: self.rhs,
            }
        }


class MongoIn(MongoLookup):
    """MongoDB Query Node for RelatedIn"""

    filter_operator = "$in"

    def _get_mongo_search(self, compiler, connection) -> dict:
        if self.lhs.target.attname not in self.mongo_meta["search_fields"]:
            return {}
        return {
            "in": {
                "path": self.lhs.target.column,
                "value": self.rhs,
            }
        }


class MongoRelatedIn(MongoIn):
    filter_operator = "$in"


class MongoEqualityComparison(MongoLookup):
    """MongoDB Query Node for LessThanOrEqual"""

    filter_operator: str

    def __init__(
        self,
        operator: LessThan | LessThanOrEqual | GreaterThan | GreaterThanOrEqual,
        mongo_meta,
    ):
        super().__init__(operator, mongo_meta)
        self.filter_operator = {
            LessThan: "$lt",
            LessThanOrEqual: "$lte",
            GreaterThan: "$gt",
            GreaterThanOrEqual: "$gte",
        }[type(operator)]

    def _get_mongo_search(self, compiler, connection) -> dict:
        return {
            "range": {
                "path": self.lhs.target.column,
                self.filter_operator[1:-1]: self.rhs,
            }
        }


class SearchNode(Node):
    """MongoDB Search Query Base Node"""

    def __init__(self, node: Expression, mongo_meta):
        super().__init__(node, mongo_meta)

    def requires_search(self) -> bool:
        return True

    def get_mongo_query(self, compiler, connection, is_search=False) -> dict:
        if not is_search:
            raise RequiresSearchException("SearchNode requires application in search pipeline.")
        else:
            return {}

    def get_mongo_search(self, compiler, connection) -> dict:
        return self._get_mongo_search(compiler, connection)

    @abstractmethod
    def _get_mongo_search(self, compiler, connection) -> dict: ...


class MongoSearchLookup(SearchNode):
    """MongoDB Search Query Node for SearchVectorExact"""

    def __init__(self, exact: Lookup, mongo_meta):
        super().__init__(exact, mongo_meta)
        self.lhs: SearchVector = exact.lhs
        self.rhs: SearchQuery = exact.rhs


class MongoSearchVectorExact(MongoSearchLookup):
    """Maps search vector to basic MongoDB wildcard query"""

    def _get_mongo_search(self, compiler, connection) -> dict:
        rhs_expressions = self.lhs.get_source_expressions()
        lhs_expressions = self.rhs.get_source_expressions()
        attname_to_column = {
            expression.field.attname: expression.field.column for expression in rhs_expressions
        }
        query = [expression.value for expression in lhs_expressions]
        if set(attname_to_column.keys()) - set(self.mongo_meta["search_fields"].keys()):
            raise RequiresSearchIndex(
                "SearchVectorExact requires a search index for the fields used in the search."
            )
        # weight = lhs.weight
        # config = lhs.config
        auto_complete_columns = [
            attname_to_column[key]
            for key, value in self.mongo_meta["search_fields"].items()
            if "autocomplete" in value and key in attname_to_column
        ]
        query_columns = [
            attname_to_column[key]
            for key, value in self.mongo_meta["search_fields"].items()
            if "string" in value and key not in auto_complete_columns and key in attname_to_column
        ]

        search_query = dict()
        if auto_complete_columns and query_columns:
            search_query = {
                "compound": {
                    "should": [
                        {"wildcard": {"path": query_columns, "query": query}},
                        *[
                            {"autocomplete": {"path": column, "query": query}}
                            for column in auto_complete_columns
                        ],
                    ]
                }
            }
        elif auto_complete_columns:
            search_query = {"autocomplete": {"path": auto_complete_columns, "query": query}}
        elif query_columns:
            search_query = {"wildcard": {"path": query_columns, "query": query}}
        return search_query


class MongoNothingNode(Node):
    def get_mongo_query(self, compiler, connection, is_search=...) -> dict:
        return {"$expr": {"$eq": [True, False]}}

    def get_mongo_search(self, compiler, connection) -> dict:
        return {}


class MongoWhereNode:
    """MongoDB Query Node for WhereNode"""

    node_map = {
        NothingNode: MongoNothingNode,
        Exact: MongoExact,
        IntegerFieldExact: MongoExact,
        RelatedIn: MongoRelatedIn,
        RelatedExact: MongoExact,
        In: MongoIn,
        LessThan: MongoEqualityComparison,
        LessThanOrEqual: MongoEqualityComparison,
        GreaterThan: MongoEqualityComparison,
        GreaterThanOrEqual: MongoEqualityComparison,
        SearchVectorExact: MongoSearchVectorExact,
        RawMongoDBQuery: RawMongoQueryExpression,
    }

    def __init__(self, where: WhereNode, mongo_meta):
        self.node = where
        self.connector = where.connector
        self.children: list[MongoWhereNode | Node] = []
        self.mongo_meta = mongo_meta
        self.negated = where.negated
        for child in self.node.children:
            if isinstance(child, WhereNode):
                self.children.append(MongoWhereNode(child, self.mongo_meta))
            elif isinstance(child, Exact) and isinstance(child.lhs, RawMongoDBQuery):
                self.children.append(RawMongoQueryExpression(child.lhs, self.mongo_meta))
            elif child.__class__ in self.node_map:
                self.children.append(self.node_map[child.__class__](child, self.mongo_meta))
            else:
                raise NotImplementedError(f"Node not implemented: {type(child)}")

    def __bool__(self):
        return len(self.children) > 0

    def requires_search(self) -> bool:
        return any(child.requires_search() for child in self.children)

    def get_mongo_query(self, compiler, connection, is_search=False) -> dict:
        child_queries = list(
            filter(
                bool,
                [
                    child.get_mongo_query(compiler, connection, is_search=is_search)
                    for child in self.children
                ],
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

    def get_mongo_search(self, compiler, connection) -> dict:
        child_queries = list(
            filter(
                bool,
                [child.get_mongo_search(compiler, connection) for child in self.children],
            )
        )
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
    def __init__(self, col: Count, alias: str | None, mongo_meta):
        self.col = col
        self.mongo_meta = mongo_meta
        self.alias = alias

    def get_mongo(self):
        return {
            "$group": {"_id": None, "_count": {"$sum": 1}},
            "$project": {
                "_id": None,
                (self.alias or self.col.output_field.column): "$_count",
            },
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
