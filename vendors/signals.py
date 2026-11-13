# vendors/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import VendorProfile

@receiver(post_save, sender=VendorProfile)
def promote_user_on_approval(sender, instance, **kwargs):
    user = instance.user
    if instance.status == 'approved' and user.role != 'vendor':
        user.role = 'vendor'
        user.save(update_fields=['role'])