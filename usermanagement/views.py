from django.shortcuts import redirect, render
from django.contrib.auth import login
from .forms import RegistrationForm
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib import messages
from usermanagement.models import User, UserProfile, Driver
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from recovery.models import RecoveryRequest
from services.models import Service
from usermanagement.models import Driver, User, UserProfile



# Create your views here.
def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home') 
    else:
        form = RegistrationForm()
    return render(request, 'usermanagement/register.html', {'form': form})


def signup(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')
        role = request.POST.get('role')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'usermanagement/signup.html', {'form_data': request.POST})

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'usermanagement/signup.html', {'form_data': request.POST})

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'usermanagement/signup.html', {'form_data': request.POST})

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=role,
        )

        UserProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            address=request.POST.get('address'),
        )

        messages.success(request, 'Account created successfully!')
        return redirect('login')

    return render(request, 'usermanagement/register.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'usermanagement/login.html')

@login_required
def dashboard(request):
    if request.user.role == 'ADMIN':
        total_users = User.objects.count()
        online_drivers = Driver.objects.filter(status='AVAILABLE').count()
        drivers = Driver.objects.select_related('user').all()
        return render(request, 'usermanagement/admin_dashboard.html', {
            'total_users': total_users,
            'online_drivers': online_drivers,
            'avg_response': 32,
            'drivers': drivers,
        })
    elif request.user.role == 'DRIVER':
        return render(request, 'usermanagement/driver_dashboard.html')
    else:
        return render(request, 'usermanagement/member_dashboard.html')

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required(login_url="login")
def admin_dashboard(request):
    if request.user.role != User.Role.ADMIN:
        return redirect("home")

    users = User.objects.all()
    drivers = Driver.objects.select_related("user").all()
    services = Service.objects.all()
    requests = RecoveryRequest.objects.select_related("member", "service").all()

    context = {
        "total_users": users.count(),
        "total_drivers": drivers.count(),
        "total_requests": requests.count(),
        "total_services": services.count(),
        "active_requests": requests.filter(status__in=["PENDING", "IN_PROGRESS", "ASSIGNED"]).count(),
        "users": users,
        "drivers": drivers,
        "services": services,
        "requests": requests,
        "user_roles": User.Role.choices,
        "driver_statuses": Driver.Status.choices,
        "vehicle_types": Driver.VehicleType.choices,
    }
    return render(request, "usermanagement/admin_dashboard.html", context)


@login_required(login_url="login")
def admin_create_user(request):
    if request.user.role != User.Role.ADMIN:
        return redirect("home")
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        role = request.POST.get("role", User.Role.MEMBER)
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")
        phone = request.POST.get("phone", "")
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return redirect("admin_dashboard")
        user = User.objects.create_user(username=username, email=email, password=password, role=role)
        UserProfile.objects.create(user=user, first_name=first_name, last_name=last_name, phone=phone)
        messages.success(request, f"User '{username}' created successfully.")
    return redirect("admin_dashboard")


@login_required(login_url="login")
def admin_create_driver(request):
    if request.user.role != User.Role.ADMIN:
        return redirect("home")
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        license_number = request.POST.get("license_number")
        vehicle_type = request.POST.get("vehicle_type")
        vehicle_registration = request.POST.get("vehicle_registration")
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return redirect("admin_dashboard")
        user = User.objects.create_user(username=username, email=email, password=password, role=User.Role.DRIVER)
        Driver.objects.create(user=user, license_number=license_number, vehicle_type=vehicle_type, vehicle_registration=vehicle_registration, qualification=[], specialization=[])
        messages.success(request, f"Driver '{username}' created successfully.")
    return redirect("admin_dashboard")


@login_required(login_url="login")
def admin_create_service(request):
    if request.user.role != User.Role.ADMIN:
        return redirect("home")
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description", "")
        price = request.POST.get("price")
        estimated_duration = request.POST.get("estimated_duration")
        Service.objects.create(name=name, description=description, price=price, estimated_duration=estimated_duration)
        messages.success(request, f"Service '{name}' created successfully.")
    return redirect("admin_dashboard")


@login_required(login_url="login")
def admin_delete_user(request, user_id):
    if request.user.role != User.Role.ADMIN:
        return redirect("home")
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
    else:
        user.delete()
        messages.success(request, f"User '{user.username}' deleted.")
    return redirect("admin_dashboard")


@login_required(login_url="login")
def admin_delete_service(request, service_id):
    if request.user.role != User.Role.ADMIN:
        return redirect("home")
    service = get_object_or_404(Service, id=service_id)
    service.delete()
    messages.success(request, f"Service '{service.name}' deleted.")
    return redirect("admin_dashboard")
