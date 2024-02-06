from django.db import models
from django.db.models import JSONField

from django_mongodb.managers import MongoManager


class FooModel(models.Model):
    objects: MongoManager = MongoManager()

    json_field = JSONField()
    name = models.CharField(max_length=100)
    name2 = models.CharField(max_length=100, null=True, db_column="name_2")
    datetime_field = models.DateTimeField(auto_now_add=True)
    time_field = models.TimeField(auto_now_add=True)
    date_field = models.DateField(auto_now_add=True)

    class MongoMeta:
        search_fields = {"name": ["string"], "name2": ["string"]}


class SameTableChild(FooModel):
    dummy_model_ptr = models.OneToOneField(
        FooModel,
        on_delete=models.CASCADE,
        parent_link=True,
        related_name="child_type",
        db_column="_id",
    )
    extended = models.CharField(max_length=100)

    class Meta:
        db_table = "testapp_foomodel"


class SameTableOneToOne(models.Model):
    dummy_model = models.OneToOneField(
        FooModel,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="extends",
        db_column="_id",
    )
    extra = models.CharField(max_length=100)

    class Meta:
        db_table = "testapp_foomodel"


class DifferentTableOneToOne(models.Model):
    dummy_model = models.OneToOneField(
        FooModel,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="another_extends",
        db_column="_id",
    )
    extra = models.CharField(max_length=100)


class RelatedModel(models.Model):
    name = models.CharField(max_length=100)
    foo = models.ForeignKey(FooModel, on_delete=models.CASCADE, related_name="related")
