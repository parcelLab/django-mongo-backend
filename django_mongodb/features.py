from django.db.backends.base.features import BaseDatabaseFeatures


class DatabaseFeatures(BaseDatabaseFeatures):
    supports_transactions = False
    supports_explaining_query_execution = False
    supports_json_field = True
    has_native_json_field = True
