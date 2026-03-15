from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from usermanagement.models import User, UserProfile, Driver, DriverLocation
# Register your models here.
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'active', 'is_staff')
    list_filter = ('role', 'active', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('uuid', 'role', 'active', 'deleted_at')}),
    )
    readonly_fields = ('uuid')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'last_name', 'phone', 'membership_tier')
    list_filter = ('membership_tier',)

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'vehicle_type', 'license_number', 'acceptance_rate')
    list_filter = ('status', 'vehicle_type')
 
 
@admin.register(DriverLocation)
class DriverLocationAdmin(admin.ModelAdmin):
    list_display = ('driver', 'latitude', 'longitude', 'is_current', 'created_at')
    list_filter = ('is_current',)