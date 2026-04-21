from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from usermanagement.views import admin_handle_request, admin_requests_status, admin_recovery_requests_api, admin_users, assign_recovery_request, cancel_driver_assignment, complete_driver_assignment, decline_recovery_request, driver_assignment_snapshot, driver_dispatch_card, driver_requests, login_view, members, member_requests_status, register_view, request_driver_assistance, signup, dashboard, logout_view, admin_create_user, admin_create_driver, admin_delete_user, admin_delete_service, admin_users, admin_recovery_requests, admin_analytics, admin_services, submit_request, lookup_vehicle, cancel_request, get_driver_locations, update_driver_location, update_driver_status, accept_driver_assignment, member_request_driver_location

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
    path('dashboard/analytics/', admin_analytics, name='admin_analytics'),
    path('dashboard/services/', admin_services, name='admin_services'),
    path('dashboard/delete-user/<uuid:user_id>/', admin_delete_user, name='admin_delete_user'),
    path('dashboard/delete-service/<int:service_id>/', admin_delete_service, name='admin_delete_service'),
    path('dashboard/admin-users/', admin_users, name='admin_users'),
    path('dashboard/driver-requests/', driver_requests, name='driver_requests'),
    path('dashboard/handle-request/<uuid:request_id>/', admin_handle_request, name='admin_handle_request'),
    path('submit-request/', submit_request, name='submit_request'),
    path('cancel-request/<int:request_id>/', cancel_request, name='cancel_request'),
    path('lookup-vehicle/', lookup_vehicle, name='lookup_vehicle'),
    path('api/driver-locations/', get_driver_locations, name='get_driver_locations'),
    path('api/admin-requests-status/', admin_requests_status, name='admin_requests_status'),
    path('api/admin-recovery-requests/', admin_recovery_requests_api, name='admin_recovery_requests_api'),
    path('api/member-requests-status/', member_requests_status, name='member_requests_status'),
    path('api/member-request-driver-location/<int:request_id>/', member_request_driver_location, name='member_request_driver_location'),
    path('api/update-location/', update_driver_location, name='update_driver_location'),
    path('api/update-driver-status/', update_driver_status, name='update_driver_status'),
    path('api/driver-assignment-snapshot/', driver_assignment_snapshot, name='driver_assignment_snapshot'),
    path('api/driver-dispatch-card/', driver_dispatch_card, name='driver_dispatch_card'),
    path('api/accept-driver-assignment/', accept_driver_assignment, name='accept_driver_assignment'),
    path('api/complete-driver-assignment/', complete_driver_assignment, name='complete_driver_assignment'),
    path('api/cancel-driver-assignment/', cancel_driver_assignment, name='cancel_driver_assignment'),
    path('api/request-driver-assistance/', request_driver_assistance, name='request_driver_assistance'),
    path('dashboard/recovery-requests/<int:request_id>/decline/', decline_recovery_request, name='decline_recovery_request'),

    # FR-0003 — Password reset flow (Django's built-in views + project templates).
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
]
