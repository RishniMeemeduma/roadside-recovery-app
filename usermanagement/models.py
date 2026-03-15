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