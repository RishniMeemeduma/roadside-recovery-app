from django.urls import path
from django.contrib import admin
from usermanagement.views import admin_handle_request, admin_users, assign_recovery_request, decline_recovery_request, driver_requests, login_view, members, register_view, signup, dashboard, logout_view, admin_create_user, admin_create_driver, admin_delete_user, admin_delete_service, admin_users, admin_recovery_requests, admin_analytics, admin_services, submit_request, lookup_vehicle, cancel_request, get_driver_locations, update_driver_location, update_driver_status

urlpatterns = [
    path('register/', register_view, name='register'),
    path('signup/', signup, name='signup'),
    path('login/', login_view, name='login'),
    path('dashboard/', dashboard, name='dashboard'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/create-user/', admin_create_user, name='admin_create_user'),
    path('dashboard/create-driver/', admin_create_driver, name='admin_create_driver'),
    path('dashboard/members/', members, name='members'),
    path('dashboard/recovery-requests/', admin_recovery_requests, name='admin_recovery_requests'),
    path('dashboard/recovery-requests/<int:request_id>/assign/', assign_recovery_request, name='assign_recovery_request'),
    path('dashboard/recovery-requests/<int:request_id>/decline/', decline_recovery_request, name='decline_recovery_request'),
    path('dashboard/analytics/', admin_analytics, name='admin_analytics'),
    path('dashboard/services/', admin_services, name='admin_services'),
    path('dashboard/create-user/', admin_create_user, name='admin_create_user'),
    path('dashboard/create-driver/', admin_create_driver, name='admin_create_driver'),
    path('dashboard/delete-user/<uuid:user_id>/', admin_delete_user, name='admin_delete_user'),
    path('dashboard/delete-service/<int:service_id>/', admin_delete_service, name='admin_delete_service'),
    path('dashboard/admin-users/', admin_users, name='admin_users'),
    path('dashboard/driver-requests/', driver_requests, name='driver_requests'),
    path('dashboard/handle-request/<uuid:request_id>/', admin_handle_request, name='admin_handle_request'),
    path('submit-request/', submit_request, name='submit_request'),
    path('cancel-request/<int:request_id>/', cancel_request, name='cancel_request'),
    path('lookup-vehicle/', lookup_vehicle, name='lookup_vehicle'),
    path('api/driver-locations/', get_driver_locations, name='get_driver_locations'),
    path('api/update-location/', update_driver_location, name='update_driver_location'),
    path('api/update-driver-status/', update_driver_status, name='update_driver_status'),
]
