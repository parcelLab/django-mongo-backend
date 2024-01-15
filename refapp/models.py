from django.db import models


class RefModel(models.Model):
    name = models.CharField(max_length=100)
    json = models.JSONField(default=dict)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
