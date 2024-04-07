from dataclasses import dataclass

from django.db.backends.base.introspection import BaseDatabaseIntrospection


@dataclass
class TableInfo:
    name: str
    type: str


class DatabaseIntrospection(BaseDatabaseIntrospection):
    def get_table_list(self, cursor):
        with self.connection.cursor() as conn:
            return [
                TableInfo(name=name, type="t") for name in conn.connection.list_collection_names()
            ]
