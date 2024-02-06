from django.db.backends.base.client import BaseDatabaseClient


class DatabaseClient(BaseDatabaseClient):
    executable_name = "django_mongodb"

    def runshell(self):
        raise NotImplementedError("runshell() isn't implemented.")
