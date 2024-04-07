## Django backend for MongoDB

Django backend for MongoDB.

Supports:
- Column mappings to MongoDB documents
- Single table (collection) inheritance and single table OneToOne relationships
- Filters (filter/exclude)

## Setup / Configuration

Not supported as primary database, as Django contrib apps rely on Integer primary keys in built in migrations (and
because it is a use case that is not a priority at the moment).

```python
# settings.py
DATABASES = {
    # or any other primary databse
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    # mongodb database, Client constructor options are passe in 'CLIENT', the database name in 'NAME'
    "mongodb": {
        "ENGINE": "django_mongodb",
        "NAME": "django_mongodb",
        "CONN_MAX_AGE": 120,
        "CLIENT": {
            "host": os.environ.get("MONGODB_URL"),
        },
    },
}
# A database is required
DATABASE_ROUTERS = ["testproject.router.DatabaseRouter"]
```

Using the database in models requires a DatabaseRouter, which could look like this
```python
class DatabaseRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == "mymongoapp":
            return "default"
        return "default"

    def db_for_write(self, model, **hints):
        if model._meta.app_label == "mymongoapp":
            return "default"
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label == obj2._meta.app_label:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == "mymongoapp":
            # we are disabling migrations, as MongoDB is schema-less. Alerts, such as renaming fields, etc. are not supported
            return False
        return None
```

Finally we are going to change the default primary key of the app using MongoDB (if that is the case, otherwise add
ObjectIdAutoField to the models, where you need it).

```python
# apps.py
class TestappConfig(AppConfig):
    default_auto_field = "django_mongodb.models.ObjectIdAutoField"
    name = "mymongoapp"
```

### Defining Models
A simple model, in an app, which has `ObjectIdAutoField` as `default_auto_field`

```python
class MyModel(models.Model):
    json_field = JSONField()
    name = models.CharField(max_length=100)
    datetime_field = models.DateTimeField(auto_now_add=True)
    time_field = models.TimeField(auto_now_add=True)
    date_field = models.DateField(auto_now_add=True)
```

Single table inheritance

```python
class SameTableChild(MyModel):
    my_model_ptr = models.OneToOneField(
        MyModel,
        on_delete=models.CASCADE,
        parent_link=True,
        related_name="same_table_child",
        # pointer to the primary key of the parent model
        db_column="_id",
    )
    extended = models.CharField(max_length=100)

    class Meta:
        # We are using the parent collection as db_table
        db_table = "mymongoapp_mymodel"
```

Single table `OneToOne` relationships

```python
class SameTableOneToOne(models.Model):
    dummy_model = models.OneToOneField(
        MyModel,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="extends",
        db_column="_id",
    )
    extra = models.CharField(max_length=100)

    class Meta:
        # we are using the same collection to persist one-to-one relationships
        db_table = "mymongoapp_mymodel"
```

### Querying

```python
# get all objects
MyModel.objects.all()

# get all objects, which have a name in list ["foo", "bar"]
MyModel.objects.filter(name_in=["foo", "bar"])

# select related with single table inheritance and one to one relationships
MyModel.objects.select_related("same_table_child", "extends").all()

# simple aggregations
MyModel.objects.filter(name_in=["foo", "bar"]).count()
```

### Search
Using the `prefer_search()` extension of MongoQueryset, we can use the `$search` operator of MongoDB to query,
if we have search indexes configured on the model.

```python
MyModel.objects.prefer_search().filter(name="foo").all()
```

PostgreSQL search vectors map down to MongoDB search indexes, so we can use the same syntax as with PostgreSQL.

```python
class MyModel(models.Model):
    name = models.CharField(max_length=100)
```

```python
MyModel.objects.annotate(search=SearchVector('name')).filter(search=SearchQuery('foo')).all()
```

### Raw Queries

```python
with connections["mongodb"].cursor() as cursor:
    doc = cursor.collections["my_collection"].find_one()
    assert isinstance(doc["_id"], ObjectId)
```
