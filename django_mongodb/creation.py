from django.conf import settings
from django.db.backends.base.creation import BaseDatabaseCreation


class DatabaseCreation(BaseDatabaseCreation):
    # mongodump --archive --db=test | mongorestore --archive  --nsFrom='test.*' --nsTo='examples.*'
    def create_test_db(self, verbosity=1, autoclobber=False, serialize=True, keepdb=False):
        test_database_name = self._get_test_db_name()
        if not keepdb:
            with self.connection._nodb_cursor() as cur:
                cur.drop_database(test_database_name)
        settings.DATABASES[self.connection.alias]["NAME"] = test_database_name
        return test_database_name

    def _destroy_test_db(self, test_database_name, verbosity):
        with self.connection._nodb_cursor() as cur:
            cur.drop_database(test_database_name)
