from django.urls import path
from django.contrib import admin
from usermanagement.views import login_view, register_view, signup, dashboard, logout_view, admin_create_user, admin_create_driver, admin_create_service, admin_delete_user, admin_delete_service

urlpatterns = [
    path('register/', register_view, name='register'),
    path('signup/', signup, name='signup'),
    path('login/', login_view, name='login'),
    path('dashboard/', dashboard, name='dashboard'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/create-user/', admin_create_user, name='admin_create_user'),
    path('dashboard/create-driver/', admin_create_driver, name='admin_create_driver'),
    path('dashboard/create-service/', admin_create_service, name='admin_create_service'),
    path('dashboard/delete-user/<int:user_id>/', admin_delete_user, name='admin_delete_user'),
    path('dashboard/delete-service/<int:service_id>/', admin_delete_service, name='admin_delete_service'),

]
