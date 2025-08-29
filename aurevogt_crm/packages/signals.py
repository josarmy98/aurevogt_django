from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Package, PackageEvent

@receiver(pre_save, sender=Package)
def _keep_prev_status(sender, instance, **kwargs):
    if instance.pk:
        instance._prev_status = Package.objects.get(pk=instance.pk).status

@receiver(post_save, sender=Package)
def _log_event(sender, instance, created, **kwargs):
    prev = getattr(instance, "_prev_status", None)
    if created:
        PackageEvent.objects.create(package=instance, type="created", status_from="", status_to=instance.status)
    elif prev and prev != instance.status:
        PackageEvent.objects.create(package=instance, type="updated", status_from=prev, status_to=instance.status)