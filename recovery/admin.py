from django.contrib import admin
from recovery.models import RecoveryRequest, Assignment, JobHistory


@admin.register(RecoveryRequest)
class RecoveryRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'member', 'service', 'status', 'priority', 'place', 'created_at')
    list_filter = ('status', 'priority', 'place')


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'driver', 'driver_response', 'offer_sent_at')
    list_filter = ('driver_response',)


@admin.register(JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'driver', 'start_time', 'end_time', 'completion_time_minutes', 'member_rating')
