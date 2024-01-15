from itertools import chain

from django.db.models.sql.compiler import (
    SQLCompiler as BaseSQLCompiler,
    SQLInsertCompiler as BaseSQLInsertCompiler,
)
from django.db.models.sql.constants import (
    MULTI,
    GET_ITERATOR_CHUNK_SIZE,
    NO_RESULTS,
    SINGLE,
    CURSOR,
)
from pymongo import InsertOne, UpdateOne

from django_mongodb.query import MongoWhereNode, MongoOrdering, MongoSelect


class SQLCompiler(BaseSQLCompiler):
    def build_filter(self, filter_expr):
        return MongoWhereNode(filter_expr, self.get_mongo_meta()).get_mongo_query()

    def as_operation(self, with_limits=True, with_col_aliases=False):
        combinator = self.query.combinator
        extra_select, order_by, group_by = self.pre_sql_setup(
            with_col_aliases=with_col_aliases or bool(combinator),
        )
        if combinator or extra_select or group_by or with_col_aliases or self.query.distinct:
            raise NotImplementedError

        # Is a LIMIT/OFFSET clause needed?
        with_limit_offset = with_limits and self.query.is_sliced
        if self.query.select_for_update:
            raise NotImplementedError

        pipeline = []
        if self.where:
            filter = self.build_filter(self.where)
            pipeline.append({"$match": filter})

        if self.query.order_by:
            order = MongoOrdering(self.query).get_mongo_order()
            pipeline.append({"$sort": order})

        if with_limit_offset and self.query.low_mark:
            pipeline.append({"$skip": self.query.low_mark})

        if with_limit_offset and self.query.high_mark:
            pipeline.append({"$limit": self.query.high_mark})

        if select_cols := self.select + extra_select:
            select_pipeline = MongoSelect(select_cols, self.get_mongo_meta()).get_mongo()
            pipeline.extend(select_pipeline)

        referenced_tables = set()
        for key, item in self.query.alias_refcount.items():
            if item < 1:
                continue
            else:
                referenced_tables.add(self.query.alias_map[key].table_name)

        if len(referenced_tables) > 1:
            raise NotImplementedError("Multi-table joins are not implemented yet.")

        return {
            "collection": self.query.model._meta.db_table,
            "op": "aggregate",
            "pipeline": [
                *pipeline,
            ],
        }

    def get_mongo_meta(self):
        if hasattr(self.query.model, "MongoMeta"):
            _meta = self.query.model.MongoMeta
            return {
                "search_fields": {} if not hasattr(_meta, "search_fields") else _meta.search_fields
            }
        else:
            return {"search_fields": {}}

    def execute_sql(
        self, result_type=MULTI, chunked_fetch=False, chunk_size=GET_ITERATOR_CHUNK_SIZE
    ):
        result_type = result_type or NO_RESULTS
        self.setup_query()

        # Join handling, currently only pseudo-joins on same collection
        # for same collection inheritance
        if self.query.extra_tables:
            raise NotImplementedError("Can't do subqueries with multiple tables yet.")

        cursor = self.connection.cursor()
        try:
            cursor.execute(self.as_operation())
        except Exception:
            cursor.close()
            raise

        if result_type == CURSOR:
            return cursor
        if result_type == SINGLE:
            return cursor.fetchone()
        if result_type == NO_RESULTS:
            cursor.close()
            return

        result = cursor_iter(
            cursor,
            self.connection.features.empty_fetchmany_value,
            None,
            chunk_size,
        )
        return result

    def apply_converters(self, rows, converters):
        connection = self.connection
        converters = list(converters.items())
        for row in map(list, rows):
            for pos, (convs, expression) in converters:
                value = row[pos]
                for converter in convs:
                    # MongoDB returns JSON fields as native dict already
                    if expression.output_field.db_type(connection) == "json":
                        continue
                    value = converter(value, expression, connection)
                row[pos] = value
            yield row

    def results_iter(
        self,
        results=None,
        tuple_expected=False,
        chunked_fetch=False,
        chunk_size=GET_ITERATOR_CHUNK_SIZE,
    ):
        """Return an iterator over the results from executing this query."""
        if results is None:
            results = self.execute_sql(MULTI, chunked_fetch=chunked_fetch, chunk_size=chunk_size)
        fields = [s[0] for s in self.select[0 : self.col_count]]
        converters = self.get_converters(fields)
        rows = chain.from_iterable(results)
        # Temporary mapping of dict to tuple, until we move this to 'project'
        _row_tuples = []
        fields = [s[0] for s in self.select[0 : self.col_count]]
        for row in rows:
            _row_tuples.append(tuple(row[field.target.column] for field in fields))

        if converters:
            _row_tuples = self.apply_converters(_row_tuples, converters)
            if tuple_expected:
                _row_tuples = map(tuple, _row_tuples)
        for row in _row_tuples:
            yield row


def cursor_iter(cursor, sentinel, col_count, itersize):
    """
    Yield blocks of rows from a cursor and ensure the cursor is closed when
    done.
    """
    try:
        for rows in iter((lambda: cursor.fetchmany(itersize)), sentinel):
            yield rows if col_count is None else [r[:col_count] for r in rows]
    finally:
        cursor.close()


class SQLDeleteCompiler(SQLCompiler):
    def as_operation(self, with_limits=True, with_col_aliases=False):
        opts = self.query.get_meta()
        filter = self.build_filter(self.query.where)
        return {
            "collection": opts.db_table,
            "op": "delete_many",
            "filter": filter,
        }


class SQLInsertCompiler(SQLCompiler, BaseSQLInsertCompiler):
    compiler = "SQLInsertCompiler"

    def as_operation(self):
        # We don't need quote_name_unless_alias() here, since these are all
        # going to be column names (so we can avoid the extra overhead).
        opts = self.query.get_meta()
        fields = self.query.fields or [opts.pk]

        if len(self.query.objs) == 1 and self.returning_fields:
            return {
                "collection": opts.db_table,
                "op": "insert_one",
                "document": {
                    field.column: self.prepare_value(
                        field, self.pre_save_val(field, self.query.objs[0])
                    )
                    for field in fields
                },
            }
        elif self.returning_fields:
            raise NotImplementedError(
                "Returning fields is not supported for bulk inserts, right now, though very possible"
            )
        elif self.query.fields:
            insert_statement = [
                InsertOne(
                    {
                        field.column: self.prepare_value(field, self.pre_save_val(field, obj))
                        for field in fields
                    }
                )
                if not obj.pk
                #  need to upsert if pk is given, because we support single collection inheritance
                else UpdateOne(
                    {opts.pk.column: obj.pk},
                    {
                        "$set": {
                            field.column: self.prepare_value(field, self.pre_save_val(field, obj))
                            for field in fields
                            if not field.primary_key
                        }
                    },
                    upsert=True,
                )
                for obj in self.query.objs
            ]
        else:
            # An empty object.
            insert_statement = [
                InsertOne({opts.pk.column: self.connection.ops.pk_default_value()})
                for _ in self.query.objs
            ]

        return {
            "collection": opts.db_table,
            "op": "bulk_write",
            "requests": insert_statement,
        }

    def execute_sql(self, returning_fields=None):
        assert not (
            returning_fields
            and len(self.query.objs) != 1
            and not self.connection.features.can_return_rows_from_bulk_insert
        )
        opts = self.query.get_meta()
        self.returning_fields = returning_fields
        with self.connection.cursor() as cursor:
            cursor.execute(self.as_operation(), None)
            if not self.returning_fields:
                return []
            else:
                rows = [
                    (
                        self.connection.ops.last_insert_id(
                            cursor,
                            opts.db_table,
                            opts.pk.column,
                        ),
                    )
                ]
        return rows


class SQLUpdateCompiler(SQLCompiler):
    def as_operation(self):
        opts = self.query.get_meta()
        filter = self.build_filter(self.query.where)
        update = {
            field[0].column: field[0].get_db_prep_save(field[2], self.connection)
            for field in self.query.values
        }
        return {
            "collection": opts.db_table,
            "op": "update_many",
            "filter": filter,
            "update": {"$set": update},
        }

    def execute_sql(self, result_type):
        """
        Execute the specified update. Return the number of rows affected by
        the primary update query. The "primary update query" is the first
        non-empty query that is executed. Row counts for any subsequent,
        related queries are not available.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(self.as_operation())
            rows = cursor.rowcount if cursor else 0
            is_empty = cursor is None
        finally:
            if cursor:
                cursor.close()
        for query in self.query.get_related_updates():
            aux_rows = query.get_compiler(self.using).execute_sql(result_type)
            if is_empty and aux_rows:
                rows = aux_rows
                is_empty = False
        return rows
