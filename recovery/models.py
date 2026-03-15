from django.db import models
from django.conf import settings


# Create your models here.
class DriverLocation(models.Model):
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='locations'
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Driver {self.driver_id} @ {self.latitude},{self.longitude}"

class RecoveryRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN-PROGRESS', 'In Progress'),
        ('ASSIGNED', 'Assigned'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('NORMAL', 'Normal'),
        ('EMERGENCY', 'Emergency'),
        ('MEDIUM', 'Medium'),
    ]
    PLACE_CHOICES = [
        ('MOTORWAY', 'Motorway'),
        ('ROAD', 'Road'),
        ('NEAR HOUSE', 'Near House'),
    ]

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recovery_requests'
    )
    service = models.ForeignKey(
        'services.Service',
        on_delete=models.CASCADE,
        related_name='recovery_requests'
    )
    location_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.CharField(max_length=255)
    issue_description = models.TextField()
    vehicle_details = models.CharField(max_length=255)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='NORMAL')
    place = models.CharField(max_length=15, choices=PLACE_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Request #{self.id} - {self.status}"