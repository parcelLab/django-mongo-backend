from django.apps import AppConfig


class TestappConfig(AppConfig):
    default_auto_field = "django_mongodb.models.ObjectIdAutoField"
    name = "testapp"
