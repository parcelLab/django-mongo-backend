## Django backend for MongoDB (PoC Stage)

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
ObjectIdAutoField to the models, where you need it)
