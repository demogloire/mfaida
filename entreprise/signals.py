# ma_app/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Location

# @receiver(post_save, sender=Location)
# def create_location(sender, instance, created, **kwargs):
#     if created:
#         nouveau_code = f"{instance.initiale}{instance.reference}"
#         Location.objects.filter(pk=instance.pk).update(code=nouveau_code)

