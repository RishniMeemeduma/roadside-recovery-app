from django.contrib import admin
from usermanagement.models import User
# Register your models here.
@admin.register(User)
class UserManagementAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email')