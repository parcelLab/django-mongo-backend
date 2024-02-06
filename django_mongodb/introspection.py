from typing import NamedTuple

from django.db.backends.base.introspection import BaseDatabaseIntrospection

TableInfo = NamedTuple(
    "TableInfo",
    [
        ("name", str),
        ("type", str),
    ],
)


class DatabaseIntrospection(BaseDatabaseIntrospection):
    def get_table_list(self, cursor):
        with self.connection.cursor() as conn:
            return [TableInfo(name, "t") for name in conn.connection.list_collection_names()]
