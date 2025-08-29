from django.db import models

class ReasonCode(models.Model):
    code = models.CharField(max_length=40, unique=True)
    label = models.CharField(max_length=120)
    def __str__(self): return self.label

class SpeedXConfig(models.Model):
    enabled = models.BooleanField(default=False)
    api_base = models.URLField(blank=True)
    api_key = models.CharField(max_length=128, blank=True)
    def __str__(self): return "SpeedX Config"