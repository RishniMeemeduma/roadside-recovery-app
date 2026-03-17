from django.contrib.auth.models import AbstractUser
import uuid;
from django.db import models
# Create your models here.
class User(AbstractUser):
    ROLE_CHOICES = (
        ('MEMBER', 'Member'),
        ('DRIVER', 'Driver'),
        ('ADMIN', 'Admin'),
    )
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    email = models.EmailField(unique=True)
    active=models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        return self.email
    
class UserProfile(models.Model):
    TIER_CHOICES = [
        ('STANDARD', 'Standard'),
        ('PREMIUM', 'Premium'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)

    phone = models.CharField(max_length=15)
    address = models.CharField(max_length=255, blank=True, null=True)
    membership_tier = models.CharField(max_length=10, choices=TIER_CHOICES, default='STANDARD')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}'s profile"
    
class Driver(models.Model): 
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        OFFLINE = 'OFFLINE', 'Offline'
        ON_TRIP = 'ON_TRIP', 'On Trip'

    class VehicleType(models.TextChoices):
        MOBILE_UNIT = 'MOBILE_UNIT', 'Mobile Unit'
        TOW_TRUCK = 'TOW_TRUCK', 'Tow Truck'
        FLATBED = 'FLATBED', 'Flatbed'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    license_number = models.CharField(max_length=50)
    vehicle_type = models.CharField(max_length=15, choices=VehicleType.choices)
    vehicle_registration = models.CharField(max_length=20)
    qualification = models.JSONField()
    specialization = models.JSONField()
    acceptance_rate = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
 
    def __str__(self):
        return f"Driver {self.user.username} - {self.status}"
    

class DriverLocation(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='locations')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    def __str__(self):
        return f"Location of Driver {self.driver_id} ({self.latitude}, {self.longitude})"
    
@property
def location_display(self):
    loc = self.locations.filter(is_current=True).first()
    if loc:
        return f"{loc.latitude}, {loc.longitude}"
    return None

@property
def uptime_display(self):
    if self.status == 'AVAILABLE' or self.status == 'IN_PROGRESS':
        from django.utils import timezone
        delta = timezone.now() - self.updated_at
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m"
    return "0m"
