import requests as http_requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render
from django.contrib.auth import login
from .forms import RegistrationForm
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib import messages
from usermanagement.models import User, UserProfile, DriverStatus
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from recovery.models import RecoveryRequest
from services.models import Service
from usermanagement.models import DriverStatus, User, UserProfile

from recovery.models import RecoveryRequest
from django.contrib import messages
from django.shortcuts import get_object_or_404



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

        services = Service.objects.filter(active=True)
        context = {'form_data': request.POST, 'services': services}

        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'usermanagement/register.html', context)

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'usermanagement/register.html', context)

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'usermanagement/register.html', context)

        if role == 'DRIVER':
            license_number = request.POST.get('license_number', '').strip()
            vehicle_type = request.POST.get('vehicle_type', '').strip()
            vehicle_registration = request.POST.get('vehicle_registration', '').strip()
            qualification = request.POST.get('qualification', '').strip()
            specialization_ids = request.POST.getlist('specialization')

            if not license_number or not vehicle_type or not vehicle_registration or not qualification:
                messages.error(request, 'All driver fields are required.')
                return render(request, 'usermanagement/register.html', context)

            if not specialization_ids:
                messages.error(request, 'Please select at least one specialization.')
                return render(request, 'usermanagement/register.html', context)

            if vehicle_type not in ['MOBILE_UNIT', 'TOW_TRUCK', 'FLATBED']:
                messages.error(request, 'Invalid vehicle type.')
                return render(request, 'usermanagement/register.html', context)

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

        if role == 'DRIVER':
            import json
            try:
                qualification_data = json.loads(qualification)
            except (json.JSONDecodeError, TypeError):
                qualification_data = [q.strip() for q in qualification.split(',') if q.strip()]

            specialization_data = [int(sid) for sid in specialization_ids]

            DriverStatus.objects.create(
                user=user,
                license_number=license_number,
                vehicle_type=vehicle_type,
                vehicle_registration=vehicle_registration,
                qualification=qualification_data,
                specialization=specialization_data,
            )

        messages.success(request, 'Account created successfully!')
        return redirect('login')

    services = Service.objects.filter(active=True)
    return render(request, 'usermanagement/register.html', {'services': services})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None and user.active:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'usermanagement/login.html')

@login_required
def dashboard(request):
    if request.user.role == 'ADMIN':
        active_jobs = RecoveryRequest.objects.filter(
            status__in=['PENDING', 'IN_PROGRESS', 'ASSIGNED']
        ).count()
        online_drivers = DriverStatus.objects.filter(status='AVAILABLE', user__active=True, user__status='APPROVED', user__deleted_at__isnull=True,).count()
        drivers = DriverStatus.objects.select_related('user', 'user__profile').all()
        return render(request, 'usermanagement/admin-dashboard.html', {
            'active_jobs': active_jobs,
            'online_drivers': online_drivers,
            'avg_response': 32,
            'drivers': drivers,
        })
    elif request.user.role == 'DRIVER':
        return render(request, 'usermanagement/driver_dashboard.html')
    else:
        services = Service.objects.filter(active=True).order_by('id')
        today_requests = RecoveryRequest.objects.filter(
            member=request.user,
            created_at__date=timezone.localdate(),
            status__in=['PENDING', 'IN_PROGRESS', 'ASSIGNED']
        ).select_related('service').order_by('-created_at')
        return render(request, 'usermanagement/member_dashboard.html',
                      {
                          'services': services,
                          'today_requests': today_requests,
                      })


@login_required
@require_POST
def cancel_request(request, request_id):
    if request.user.role != 'MEMBER':
        return redirect('home')

    recovery_request = get_object_or_404(
        RecoveryRequest,
        id=request_id,
        member=request.user,
    )

    if recovery_request.status in {'COMPLETED', 'CANCELLED'}:
        messages.error(request, 'This request can no longer be cancelled.')
        return redirect('dashboard')

    recovery_request.status = 'CANCELLED'
    recovery_request.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Recovery request cancelled successfully.')
    return redirect('dashboard')

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required(login_url="login")
def admin_dashboard(request):
    if request.user.role != User.Role.ADMIN:
        return redirect("home")

    users = User.objects.all()
    drivers = DriverStatus.objects.select_related("user").all()
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
        "driver_statuses": DriverStatus.Status.choices,
        "vehicle_types": DriverStatus.VehicleType.choices,
    }
    return render(request, "usermanagement/admin-dashboard.html", context)


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
        DriverStatus.objects.create(user=user, license_number=license_number, vehicle_type=vehicle_type, vehicle_registration=vehicle_registration, qualification=[], specialization=[])
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
    user = get_object_or_404(User, uuid=user_id)
    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
    else:
        user.delete()
        messages.success(request, f"User '{user.username}' deleted.")
    return redirect("admin_dashboard")


@login_required(login_url="login")
def admin_delete_service(request, service_id):
    if request.user.role != 'ADMIN':
        return redirect("home")
    service = get_object_or_404(Service, id=service_id)
    service.delete()
    messages.success(request, f"Service '{service.name}' deleted.")
    return redirect("admin_dashboard")

@login_required
def admin_users(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    users = User.objects.filter(role='ADMIN').select_related('profile').all()
    return render(request, 'usermanagement/admin_users.html', {
        'users': users,
    })

@login_required
def members(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    members = User.objects.filter(role='MEMBER').select_related('profile').all()
    return render(request, 'usermanagement/admin_users.html', {
        'users': members,
    })

@login_required
def admin_recovery_requests(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    requests_list = RecoveryRequest.objects.select_related('member', 'service').all()
    return render(request, 'usermanagement/admin_recovery_requests.html', {
        'requests': requests_list,
    })

@login_required
def admin_analytics(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    return render(request, 'usermanagement/admin_analytics.html')

@login_required
def admin_services(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name')
            description = request.POST.get('description')
            price = request.POST.get('price')
            estimated_duration = request.POST.get('estimated_duration')
            active = request.POST.get('active') == 'on'
            Service.objects.create(
                name=name,
                description=description,
                price=price,
                estimated_duration=estimated_duration,
                active=active
            )
            messages.success(request, 'Service created successfully.')
        elif action == 'edit':
            service_id = request.POST.get('service_id')
            service = get_object_or_404(Service, id=service_id)
            service.name = request.POST.get('name')
            service.description = request.POST.get('description')
            service.price = request.POST.get('price')
            service.estimated_duration = request.POST.get('estimated_duration')
            service.active = request.POST.get('active') == 'on'
            service.save()
            messages.success(request, 'Service updated successfully.')
        return redirect('admin_services')
    services = Service.objects.filter(active=True).order_by('id')
    return render(request, 'usermanagement/admin_services.html', {
        'services': services,
    })

@login_required
def admin_delete_service(request, service_id):
    if request.user.role != 'ADMIN':
        return redirect('home')
    service = get_object_or_404(Service, id=service_id)
    service.active = False
    service.save()
    messages.success(request, 'Service deleted successfully.')
    return redirect('admin_services')

@login_required
def admin_user_requests(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    pending_requests = User.objects.filter(
        status='PENDING'
    ).select_related('profile').order_by('-date_joined')
    return render(request, 'usermanagement/admin_user_requests.html', {
        'pending_requests': pending_requests,
    })





@login_required
def driver_requests(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    pending_requests = User.objects.filter(
        role='DRIVER', status='PENDING'
    ).select_related('profile').order_by('-date_joined')
    return render(request, 'usermanagement/admin_user_requests.html', {
        'pending_requests': pending_requests,
    })

@login_required
def admin_handle_request(request, request_id):
    if request.user.role != 'ADMIN':
        return redirect('home')
    if request.method == 'POST':
        user_request = get_object_or_404(User, uuid=request_id)
        action = request.POST.get('action')
        if action == 'accept':
            user_request.status = 'APPROVED'
            user_request.active = True
            user_request.save()
            messages.success(request, f"User '{user_request.username}' approved.")
        elif action == 'decline':
            user_request.status = 'REJECTED'
            user_request.active = False
            user_request.save()
            messages.success(request, f"User '{user_request.username}' rejected.")
    return redirect('admin_user_requests')

@login_required
@require_POST
def lookup_vehicle(request):
    reg = request.POST.get('registration', '').strip().upper().replace(' ', '')
    if not reg:
        return JsonResponse({'error': 'No registration provided.'}, status=400)

    api_key = getattr(settings, 'DVLA_API_KEY', '')
    if not api_key:
        return JsonResponse({'error': 'Vehicle lookup not configured. Add DVLA_API_KEY to settings.'}, status=503)

    try:
        resp = http_requests.post(
            'https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles',
            headers={'x-api-key': api_key, 'Content-Type': 'application/json'},
            json={'registrationNumber': reg},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            return JsonResponse({
                'make': data.get('make', ''),
                'colour': data.get('colour', ''),
                'fuelType': data.get('fuelType', ''),
                'yearOfManufacture': data.get('yearOfManufacture', ''),
                'engineCapacity': data.get('engineCapacity', ''),
                'registrationNumber': data.get('registrationNumber', reg),
            })
        elif resp.status_code == 404:
            return JsonResponse({'error': 'Vehicle not found. Check the registration.'}, status=404)
        else:
            return JsonResponse({'error': 'DVLA lookup failed. Try again later.'}, status=502)
    except http_requests.exceptions.Timeout:
        return JsonResponse({'error': 'Lookup timed out. Try again.'}, status=504)
    except Exception:
        return JsonResponse({'error': 'Unexpected error during lookup.'}, status=500)


@login_required
def submit_request(request):
    if request.method == 'POST':
        service_id = request.POST.get('service_id')
        vehicle_registration = request.POST.get('vehicle_registration', '').strip()
        vehicle_details_manual = request.POST.get('vehicle_details', '').strip()
        place = request.POST.get('place', '').strip()
        details = request.POST.get('details', '').strip()
        address = request.POST.get('address', '').strip()
        latitude = request.POST.get('latitude', '0').strip() or '0'
        longitude = request.POST.get('longitude', '0').strip() or '0'

        services = Service.objects.filter(active=True).order_by('id')
        form_data = {
            'service_id': service_id,
            'vehicle_registration': vehicle_registration,
            'vehicle_details': vehicle_details_manual,
            'place': place,
            'details': details,
            'address': address,
            'latitude': latitude,
            'longitude': longitude,
        }

        def render_form(error):
            messages.error(request, error)
            return render(request, 'usermanagement/member_dashboard.html', {
                'services': services,
                'form_data': form_data,
            })

        if not service_id:
            return render_form('Please select a service type (tap one of the issue buttons).')

        missing = []
        if not vehicle_registration:
            missing.append('Vehicle Registration')
        if not vehicle_details_manual:
            missing.append('Vehicle Make & Model')
        if not details:
            missing.append('More Details')
        if not address:
            missing.append('Address')
        if missing:
            return render_form(f"These fields are required: {', '.join(missing)}")

        service = get_object_or_404(Service, id=service_id, active=True)

        try:
            latitude = f"{float(latitude):.6f}"
            longitude = f"{float(longitude):.6f}"
        except ValueError:
            latitude = '0.000000'
            longitude = '0.000000'

        if place not in {'MOTORWAY', 'ROAD', 'NEAR HOUSE'}:
            place = 'ROAD'

        if vehicle_details_manual:
            vehicle_details = f"{vehicle_registration.upper()} — {vehicle_details_manual}"
        else:
            vehicle_details = vehicle_registration.upper()

        try:
            RecoveryRequest.objects.create(
                member=request.user,
                service=service,
                location_latitude=latitude,
                location_longitude=longitude,
                address=address,
                issue_description=details,
                vehicle_details=vehicle_details[:255],
                status='PENDING',
                priority='EMERGENCY' if place == 'MOTORWAY' else 'NORMAL',
                place=place,
            )
            messages.success(request, 'Recovery request submitted successfully!')
            return redirect('dashboard')
        except Exception as e:
            return render_form(f'Could not save your request: {e}')

    return redirect('dashboard')