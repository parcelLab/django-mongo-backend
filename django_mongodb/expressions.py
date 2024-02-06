from django.db.models import Expression, fields


class RawMongoDBQuery(Expression):
    """Represent a wrapped raw mongodb query as a node within an expression."""

    query: dict

    def __init__(self, query, output_field=None):
        super().__init__(output_field=output_field)
        self.query = query

    def _resolve_output_field(self):
        return fields.BooleanField()
