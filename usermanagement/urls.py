from django.urls import path
from usermanagement.views import home

urlpatterns = [
    path('', home, name='usermanagement_home'),
]
