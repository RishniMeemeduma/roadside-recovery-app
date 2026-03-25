import requests as http_requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import RegistrationForm
from recovery.models import Assignment, RecoveryRequest, JobHistory
from services.models import Service
from usermanagement.models import DriverLocation, DriverStatus, User, UserProfile



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
        pending_qs = RecoveryRequest.objects.filter(status='PENDING').select_related('member', 'service')
        return render(request, 'usermanagement/admin-dashboard.html', {
            'active_jobs': active_jobs,
            'online_drivers': online_drivers,
            'avg_response': 32,
            'drivers': drivers,
            'new_requests': pending_qs.order_by('-created_at')[:10],
            'new_request_count': pending_qs.count(),
        })
    elif request.user.role == 'DRIVER':
        driver_status = DriverStatus.objects.select_related('user').get(user=request.user)
        # Get current assignment if any
        current_assignment = Assignment.objects.filter(
            driver=driver_status,
            driver_response=Assignment.DriverResponse.ACCEPTED
        ).select_related(
            'request__member',
            'request__service'
        ).order_by('-created_at').first()

        # Get past job history
        past_jobs = JobHistory.objects.filter(
            driver=driver_status
        ).select_related(
            'request__service',
            'request__member'
        ).order_by('-end_time')[:5]

        return render(request, 'usermanagement/driver_dashboard.html', {
            'driver_status': driver_status,
            'current_assignment': current_assignment,
            'past_jobs': past_jobs,
        })
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
    pending_qs = requests.filter(status='PENDING')
    new_requests = pending_qs.order_by('-created_at')[:10]

    context = {
        "total_users": users.count(),
        "total_drivers": drivers.count(),
        "total_requests": requests.count(),
        "total_services": services.count(),
        "active_requests": requests.filter(status__in=["PENDING", "IN_PROGRESS", "ASSIGNED"]).count(),
        "new_requests": new_requests,
        "new_request_count": pending_qs.count(),
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
    members = User.objects.filter(role__in=['MEMBER', 'DRIVER']).select_related('profile').all()
    return render(request, 'usermanagement/admin_users.html', {
        'users': members,
    })

@login_required
def admin_recovery_requests(request):
    if request.user.role != 'ADMIN':
        return redirect('home')
    requests_list = RecoveryRequest.objects.select_related('member', 'service').prefetch_related('assignments__driver__user').order_by('-created_at')
    available_drivers = DriverStatus.objects.select_related('user').filter(
        status=DriverStatus.Status.AVAILABLE,
        user__active=True,
        user__status='APPROVED',
        user__deleted_at__isnull=True,
    ).order_by('user__username')
    return render(request, 'usermanagement/admin_recovery_requests.html', {
        'requests': requests_list,
        'available_drivers': available_drivers,
    })


@login_required
def get_driver_locations(request):
    """API endpoint returning driver locations in JSON format."""
    if request.user.role != 'ADMIN':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    drivers = DriverStatus.objects.select_related('user').filter(
        status=DriverStatus.Status.AVAILABLE,
        user__active=True,
        user__status='APPROVED',
        user__deleted_at__isnull=True,
    ).order_by('user__username')

    driver_locations = []
    for driver in drivers:
        location = driver.user.usermanagement_locations.filter(is_current=True).first()
        if location:
            driver_locations.append({
                'id': driver.id,
                'name': driver.user.username,
                'latitude': float(location.latitude),
                'longitude': float(location.longitude),
                'vehicle_type': driver.vehicle_type,
                'vehicle_registration': driver.vehicle_registration,
            })

    return JsonResponse({
        'drivers': driver_locations,
        'count': len(driver_locations),
    })


@login_required
@require_POST
def update_driver_location(request):
    """API endpoint for drivers to update their location."""
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Only drivers can update location'}, status=403)

    try:
        import json
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is None or longitude is None:
            return JsonResponse({'error': 'Latitude and longitude required'}, status=400)

        # Mark old locations as not current
        DriverLocation.objects.filter(driver=request.user).update(is_current=False)

        # Create new location record
        location = DriverLocation.objects.create(
            driver=request.user,
            latitude=latitude,
            longitude=longitude,
            is_current=True,
        )

        return JsonResponse({
            'success': True,
            'latitude': float(location.latitude),
            'longitude': float(location.longitude),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def update_driver_status(request):
    """Update driver online/offline status."""
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Only drivers can update status'}, status=403)

    try:
        import json
        data = json.loads(request.body)
        status = data.get('status')

        if status not in ['AVAILABLE', 'OFFLINE']:
            return JsonResponse({'error': 'Invalid status'}, status=400)

        driver_status = DriverStatus.objects.get(user=request.user)
        driver_status.status = status
        driver_status.save(update_fields=['status', 'updated_at'])

        return JsonResponse({
            'success': True,
            'status': status,
        })
    except DriverStatus.DoesNotExist:
        return JsonResponse({'error': 'Driver status not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def assign_recovery_request(request, request_id):
    if request.user.role != 'ADMIN':
        return redirect('home')

    recovery_request = get_object_or_404(RecoveryRequest, id=request_id)
    redirect_target = f"{reverse('admin_recovery_requests')}#request-{request_id}"

    if recovery_request.status != 'PENDING':
        messages.error(request, 'Only pending requests can be assigned.')
        return redirect(redirect_target)

    driver_id = request.POST.get('driver_id')
    if not driver_id:
        messages.error(request, 'Select a driver before assigning the request.')
        return redirect(redirect_target)

    driver = get_object_or_404(
        DriverStatus.objects.select_related('user').filter(
            status=DriverStatus.Status.AVAILABLE,
            user__active=True,
            user__status='APPROVED',
            user__deleted_at__isnull=True,
        ),
        id=driver_id,
    )

    now = timezone.now()
    Assignment.objects.create(
        request=recovery_request,
        driver=driver,
        offer_sent_at=now,
        driver_response=Assignment.DriverResponse.ACCEPTED,
        driver_responded_at=now,
        accepted_at=now,
    )
    recovery_request.status = 'ASSIGNED'
    recovery_request.save(update_fields=['status', 'updated_at'])
    driver.status = DriverStatus.Status.ON_TRIP
    driver.save(update_fields=['status', 'updated_at'])

    messages.success(request, f"Request #{recovery_request.id} assigned to {driver.user.username}.")
    return redirect(redirect_target)


@login_required
@require_POST
def decline_recovery_request(request, request_id):
    if request.user.role != 'ADMIN':
        return redirect('home')

    recovery_request = get_object_or_404(RecoveryRequest, id=request_id)
    redirect_target = f"{reverse('admin_recovery_requests')}#request-{request_id}"

    if recovery_request.status in {'COMPLETED', 'CANCELLED'}:
        messages.error(request, 'This request can no longer be declined.')
        return redirect(redirect_target)

    latest_assignment = recovery_request.assignments.select_related('driver__user').order_by('-created_at').first()
    if latest_assignment and latest_assignment.driver.status == DriverStatus.Status.ON_TRIP:
        latest_assignment.cancellation_reason = 'Declined by admin'
        latest_assignment.save(update_fields=['cancellation_reason', 'updated_at'])
        latest_assignment.driver.status = DriverStatus.Status.AVAILABLE
        latest_assignment.driver.save(update_fields=['status', 'updated_at'])

    recovery_request.status = 'CANCELLED'
    recovery_request.save(update_fields=['status', 'updated_at'])
    messages.success(request, f"Request #{recovery_request.id} declined.")
    return redirect(redirect_target)

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
            recovery_request = RecoveryRequest.objects.create(
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