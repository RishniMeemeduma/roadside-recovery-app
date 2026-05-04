"""FR-0010 — notify members when their RecoveryRequest status changes.

Uses pre_save to capture the previous status, then post_save to dispatch the
email. Handling lives in signals rather than a model save() override so admin
bulk-update commands and management commands route through the same path.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string

from .models import Notification, RecoveryRequest

logger = logging.getLogger(__name__)

# Status transitions that warrant an email to the member. The PENDING -> created
# path is skipped (the member just submitted, no need to re-tell them).
_NOTIFIABLE_STATUSES = {'ASSIGNED', 'IN-PROGRESS', 'COMPLETED', 'CANCELLED'}

# Per-status copy for in-app notifications. Kept short (banner real-estate).
_IN_APP_MESSAGES = {
    'ASSIGNED': 'A driver has been assigned to your request #{id}.',
    'IN-PROGRESS': 'Your driver is on the way for request #{id}.',
    'COMPLETED': 'Your job is complete — request #{id}.',
    'CANCELLED': 'Request #{id} has been cancelled.',
}


@receiver(pre_save, sender=RecoveryRequest)
def _capture_previous_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._previous_status = sender.objects.only('status').get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=RecoveryRequest)
def _notify_member_of_status_change(sender, instance, created, **kwargs):
    previous = getattr(instance, '_previous_status', None)
    if created or previous == instance.status:
        return
    if instance.status not in _NOTIFIABLE_STATUSES:
        return

    member = instance.member
    if not getattr(member, 'email', None):
        return

    context = {
        'member': member,
        'request': instance,
        'previous_status': previous,
        'site_url': getattr(settings, 'SITE_URL', ''),
    }
    subject = render_to_string('recovery/email/status_update_subject.txt', context).strip()
    body = render_to_string('recovery/email/status_update_body.txt', context)

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            'Failed to send status-change email for RecoveryRequest %s to %s',
            instance.pk,
            member.email,
        )

    # In-app notification — persisted regardless of email outcome.
    Notification.objects.create(
        user=member,
        message=_IN_APP_MESSAGES[instance.status].format(id=instance.id),
        link='/dashboard/',
        related_request=instance,
    )
