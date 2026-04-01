import requests as http_requests
from math import atan2, cos, radians, sin, sqrt
from datetime import timedelta
from django.db import models
from django.db.models import Max
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
def _haversine_km(lat1, lon1, lat2, lon2):
    """Return great-circle distance in kilometers between two coordinates."""
    earth_radius_km = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * atan2(sqrt(a), sqrt(1 - a))


def _supports_service(driver_status, service):
    """Check if driver's specialization includes the requested service id or name."""
    specs = driver_status.specialization or []
    if not isinstance(specs, list):
        return False

    service_id_str = str(service.id)
    service_name = (service.name or '').strip().lower()
    for item in specs:
        value = str(item).strip().lower()
        if value == service_id_str or value == service_name:
            return True
    return False


DISPATCH_BATCH_SIZE = 3
DRIVER_RESPONSE_TIMEOUT_SECONDS = 60


def _rank_optimal_drivers(recovery_request, excluded_driver_ids=None):
    """Return available service-capable drivers ranked by distance."""
    excluded_driver_ids = excluded_driver_ids or set()
    req_lat = float(recovery_request.location_latitude)
    req_lon = float(recovery_request.location_longitude)

    candidate_drivers = DriverStatus.objects.select_related('user').filter(
        status=DriverStatus.Status.AVAILABLE,
        user__active=True,
        user__status='APPROVED',
        user__deleted_at__isnull=True,
    )

    ranked = []
    for driver in candidate_drivers:
        if driver.id in excluded_driver_ids:
            continue
        if not _supports_service(driver, recovery_request.service):
            continue

        current_location = driver.user.usermanagement_locations.filter(is_current=True).order_by('-updated_at').first()
        if not current_location:
            continue

        distance_km = _haversine_km(
            req_lat,
            req_lon,
            float(current_location.latitude),
            float(current_location.longitude),
        )
        ranked.append((distance_km, driver))

    ranked.sort(key=lambda item: item[0])
    return ranked


def _dispatch_to_next_optimal_drivers(recovery_request):
    """Send the request to the next nearest batch of available drivers."""
    already_offered_ids = set(
        Assignment.objects.filter(request=recovery_request).values_list('driver_id', flat=True)
    )
    ranked = _rank_optimal_drivers(recovery_request, excluded_driver_ids=already_offered_ids)
    selected = ranked[:DISPATCH_BATCH_SIZE]
    if not selected:
        recovery_request.status = 'PENDING'
        recovery_request.save(update_fields=['status', 'updated_at'])
        return 0

    now = timezone.now()
    for _, driver in selected:
        Assignment.objects.create(
            request=recovery_request,
            driver=driver,
            offer_sent_at=now,
            # Using TIMEOUT enum as "offer sent / pending response" placeholder.
            driver_response=Assignment.DriverResponse.TIMEOUT,
        )

    recovery_request.status = 'ASSIGNED'
    recovery_request.save(update_fields=['status', 'updated_at'])
    return len(selected)


def _rotate_expired_dispatch_offers(recovery_request):
    """If current offer window expired, timeout and dispatch to next nearest drivers."""
    if recovery_request.status != 'ASSIGNED':
        return 0

    # If any driver has already accepted, the request is being handled — don't rotate.
    if recovery_request.assignments.filter(
        driver_response=Assignment.DriverResponse.ACCEPTED
    ).exists():
        return 0

    pending_offers = recovery_request.assignments.filter(
        accepted_at__isnull=True,
        driver_responded_at__isnull=True,
    ).order_by('offer_sent_at')

    if not pending_offers.exists():
        return _dispatch_to_next_optimal_drivers(recovery_request)

    oldest_offer = pending_offers.first()
    expires_at = oldest_offer.offer_sent_at + timedelta(seconds=DRIVER_RESPONSE_TIMEOUT_SECONDS)
    if timezone.now() < expires_at:
        return 0

    now = timezone.now()
    pending_offers.update(
        driver_response=Assignment.DriverResponse.TIMEOUT,
        driver_responded_at=now,
        cancellation_reason='Offer expired after 60 seconds',
        updated_at=now,
    )
    return _dispatch_to_next_optimal_drivers(recovery_request)


def _get_driver_assignment_for_action(driver_status, assignment_id):
    if not assignment_id:
        raise ValueError('Assignment ID required')

    return Assignment.objects.select_related('request').get(
        id=assignment_id,
        driver=driver_status,
    )


def _get_current_driver_assignment(driver_status):
    """Return current assignment shown on driver dashboard."""
    accepted_assignment = Assignment.objects.filter(
        driver=driver_status,
        request__status__in=['ASSIGNED', 'IN-PROGRESS'],
        driver_response=Assignment.DriverResponse.ACCEPTED,
    ).select_related(
        'request__member',
        'request__service'
    ).order_by('-accepted_at', '-driver_responded_at', '-created_at').first()

    if accepted_assignment:
        return accepted_assignment

    return Assignment.objects.filter(
        driver=driver_status,
        request__status='ASSIGNED',
        accepted_at__isnull=True,
        driver_responded_at__isnull=True,
    ).select_related(
        'request__member',
        'request__service'
    ).order_by('-created_at').first()


def _get_driver_feed_snapshot(driver_status):
    """Return driver-visible dispatch feed state and a version token."""
    current_assignment = _get_current_driver_assignment(driver_status)

    relevant_assignments = Assignment.objects.filter(
        driver=driver_status,
        request__status__in=['ASSIGNED', 'IN-PROGRESS'],
    )

    assignment_ids = list(
        relevant_assignments.order_by('id').values_list('id', flat=True)
    )
    assignment_max_updated = relevant_assignments.aggregate(max_updated=Max('updated_at'))['max_updated']
    request_max_updated = relevant_assignments.aggregate(max_updated=Max('request__updated_at'))['max_updated']

    current_id = current_assignment.id if current_assignment else 0
    current_status = current_assignment.request.status if current_assignment else ''
    assignment_updated_str = assignment_max_updated.isoformat() if assignment_max_updated else ''
    request_updated_str = request_max_updated.isoformat() if request_max_updated else ''
    id_list_str = ','.join(str(aid) for aid in assignment_ids)

    feed_version = f"{current_id}|{current_status}|{assignment_updated_str}|{request_updated_str}|{id_list_str}"
    return {
        'current_assignment': current_assignment,
        'assignment_ids': assignment_ids,
        'feed_version': feed_version,
    }


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
    # Opportunistic scheduler: rotate expired offers whenever dashboard loads.
    for pending_request in RecoveryRequest.objects.select_related('service').filter(status='ASSIGNED'):
        _rotate_expired_dispatch_offers(pending_request)

    if request.user.role == 'ADMIN':
        active_jobs = RecoveryRequest.objects.filter(
            status__in=['PENDING', 'IN-PROGRESS', 'ASSIGNED']
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
        # Rotate expired offers so driver sees the latest valid dispatches.
        candidate_request_ids = Assignment.objects.filter(
            driver=driver_status,
            request__status='ASSIGNED',
            accepted_at__isnull=True,
        ).values_list('request_id', flat=True)
        for request_id in set(candidate_request_ids):
            req = RecoveryRequest.objects.select_related('service').filter(id=request_id).first()
            if req:
                _rotate_expired_dispatch_offers(req)

        driver_feed_snapshot = _get_driver_feed_snapshot(driver_status)
        current_assignment = driver_feed_snapshot['current_assignment']

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
            'driver_response_timeout_seconds': DRIVER_RESPONSE_TIMEOUT_SECONDS,
            'driver_feed_version': driver_feed_snapshot['feed_version'],
        })
    else:
        services = Service.objects.filter(active=True).order_by('id')
        today_requests = RecoveryRequest.objects.filter(
            member=request.user,
            created_at__date=timezone.localdate(),
            status__in=['PENDING', 'IN-PROGRESS', 'ASSIGNED']
        ).select_related('service').prefetch_related('assignments__driver__user__profile').order_by('-created_at')

        today_requests = list(today_requests)
        for recovery_request in today_requests:
            recovery_request.current_assignment = recovery_request.assignments.filter(
                driver_response=Assignment.DriverResponse.ACCEPTED,
            ).select_related('driver__user', 'driver__user__profile').order_by('-accepted_at', '-created_at').first()

        return render(request, 'usermanagement/member_dashboard.html',
                      {
                          'services': services,
                          'today_requests': today_requests,
                      })


@login_required
def driver_assignment_snapshot(request):
    """Return current assignment metadata so drivers can auto-refresh when dispatch changes."""
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    driver_status = get_object_or_404(DriverStatus.objects.select_related('user'), user=request.user)
    driver_feed_snapshot = _get_driver_feed_snapshot(driver_status)
    current_assignment = driver_feed_snapshot['current_assignment']

    if not current_assignment:
        return JsonResponse({
            'has_assignment': False,
            'driver_status': driver_status.status,
            'feed_version': driver_feed_snapshot['feed_version'],
            'assignment_count': len(driver_feed_snapshot['assignment_ids']),
        })

    return JsonResponse({
        'has_assignment': True,
        'driver_status': driver_status.status,
        'assignment_id': current_assignment.id,
        'request_id': current_assignment.request_id,
        'request_status': current_assignment.request.status,
        'priority': current_assignment.request.priority,
        'destination_lat': str(current_assignment.request.location_latitude),
        'destination_lon': str(current_assignment.request.location_longitude),
        'feed_version': driver_feed_snapshot['feed_version'],
        'assignment_count': len(driver_feed_snapshot['assignment_ids']),
        'offer_sent_at': current_assignment.offer_sent_at.isoformat() if current_assignment.offer_sent_at else None,
        'updated_at': current_assignment.updated_at.isoformat(),
    })


@login_required
def driver_dispatch_card(request):
    """Return the rendered dispatch card partial for live DOM injection."""
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    driver_status = get_object_or_404(
        DriverStatus.objects.select_related('user'), user=request.user
    )
    current_assignment = _get_current_driver_assignment(driver_status)
    return render(request, 'usermanagement/_dispatch_card.html', {
        'current_assignment': current_assignment,
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
        "active_requests": requests.filter(status__in=["PENDING", "IN-PROGRESS", "ASSIGNED"]).count(),
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
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")
        phone = request.POST.get("phone") or "0000000000"
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return redirect("admin_dashboard")
        user = User.objects.create_user(username=username, email=email, password=password, role=User.Role.DRIVER)
        UserProfile.objects.create(user=user, first_name=first_name, last_name=last_name, phone=phone)
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
    requests_list = RecoveryRequest.objects.select_related('member', 'service', 'job_history').prefetch_related('assignments__driver__user').order_by('-created_at')
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
def admin_requests_status(request):
    """Return live status of all active recovery requests for admin polling."""
    if request.user.role != 'ADMIN':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    active = RecoveryRequest.objects.exclude(
        status__in=['COMPLETED', 'CANCELLED']
    ).values('id', 'status')
    return JsonResponse({'requests': list(active)})


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
def member_requests_status(request):
    """Return current statuses for all of the member's today requests (used for live polling)."""
    if request.user.role != 'MEMBER':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    requests_qs = RecoveryRequest.objects.filter(
        member=request.user,
        created_at__date=timezone.localdate(),
    ).values('id', 'status')

    statuses = {str(row['id']): row['status'] for row in requests_qs}
    return JsonResponse({'statuses': statuses})


@login_required
def member_request_driver_location(request, request_id):
    """Return accepted driver details and live location for a member request."""
    if request.user.role != 'MEMBER':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    recovery_request = get_object_or_404(
        RecoveryRequest.objects.prefetch_related('assignments__driver__user__profile'),
        id=request_id,
        member=request.user,
    )
    assignment = recovery_request.assignments.filter(
        driver_response=Assignment.DriverResponse.ACCEPTED,
    ).select_related('driver__user', 'driver__user__profile').order_by('-accepted_at', '-created_at').first()

    if not assignment:
        return JsonResponse({'available': False, 'request_status': recovery_request.status})

    driver_user = assignment.driver.user
    profile = getattr(driver_user, 'profile', None)
    current_location = driver_user.usermanagement_locations.filter(is_current=True).order_by('-updated_at').first()

    return JsonResponse({
        'available': bool(current_location),
        'driver_name': driver_user.username,
        'phone': getattr(profile, 'phone', '') if profile else '',
        'vehicle_registration': assignment.driver.vehicle_registration,
        'vehicle_type': assignment.driver.vehicle_type,
        'request_status': recovery_request.status,
        'request_latitude': float(recovery_request.location_latitude),
        'request_longitude': float(recovery_request.location_longitude),
        'request_address': recovery_request.address,
        'driver_latitude': float(current_location.latitude) if current_location else None,
        'driver_longitude': float(current_location.longitude) if current_location else None,
        'updated_at': current_location.updated_at.isoformat() if current_location else None,
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
        active_job_exists = Assignment.objects.filter(
            driver=driver_status,
            driver_response=Assignment.DriverResponse.ACCEPTED,
            request__status__in=['ASSIGNED', 'IN-PROGRESS'],
        ).exists()
        if active_job_exists:
            return JsonResponse({'error': 'Complete or cancel your active job before changing availability.'}, status=409)

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
def accept_driver_assignment(request):
    """Move assigned request into in-progress state when driver starts the job."""
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Only drivers can accept assignments'}, status=403)

    try:
        import json
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')

        driver_status = DriverStatus.objects.get(user=request.user)
        assignment = _get_driver_assignment_for_action(driver_status, assignment_id)

        # Handle driver declining the offer
        action = data.get('action', 'accept')
        if action == 'decline':
            now = timezone.now()
            assignment.driver_response = Assignment.DriverResponse.DECLINED
            assignment.driver_responded_at = now
            assignment.save(update_fields=['driver_response', 'driver_responded_at', 'updated_at'])
            _dispatch_to_next_optimal_drivers(assignment.request)
            return JsonResponse({'success': True})

        if assignment.request.status != 'ASSIGNED':
            return JsonResponse({'error': 'This request is no longer available.'}, status=409)

        expiry_time = assignment.offer_sent_at + timedelta(seconds=DRIVER_RESPONSE_TIMEOUT_SECONDS)
        if timezone.now() > expiry_time:
            now = timezone.now()
            assignment.driver_response = Assignment.DriverResponse.TIMEOUT
            assignment.driver_responded_at = now
            assignment.cancellation_reason = 'Offer expired after 60 seconds'
            assignment.save(update_fields=['driver_response', 'driver_responded_at', 'cancellation_reason', 'updated_at'])

            _rotate_expired_dispatch_offers(assignment.request)
            return JsonResponse({'error': 'Offer expired. Request was forwarded to next available drivers.'}, status=409)

        assignment.driver_response = Assignment.DriverResponse.ACCEPTED
        assignment.driver_responded_at = assignment.driver_responded_at or timezone.now()
        assignment.accepted_at = assignment.accepted_at or timezone.now()
        assignment.save(update_fields=['driver_response', 'driver_responded_at', 'accepted_at', 'updated_at'])

        assignment.request.status = 'IN-PROGRESS'
        assignment.request.save(update_fields=['status', 'updated_at'])

        # Close the same request offers sent to other drivers.
        Assignment.objects.filter(request=assignment.request).exclude(id=assignment.id).filter(
            driver_responded_at__isnull=True,
            accepted_at__isnull=True,
        ).update(
            driver_response=Assignment.DriverResponse.DECLINED,
            driver_responded_at=timezone.now(),
            cancellation_reason='Taken by another driver',
            updated_at=timezone.now(),
        )

        driver_status.status = DriverStatus.Status.IN_PROGRESS
        driver_status.save(update_fields=['status', 'updated_at'])

        return JsonResponse({'success': True, 'status': assignment.request.status})
    except DriverStatus.DoesNotExist:
        return JsonResponse({'error': 'Driver status not found'}, status=404)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def decline_driver_assignment(request):
    """Driver declines a dispatch offer"""
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Only drivers can decline assignments'}, status=403)
    
    try:
        import json
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')

        driver_status = DriverStatus.objects.get(user=request.user)
        assignment = _get_driver_assignment_for_action(driver_status, assignment_id)

        if assignment.driver_response == Assignment.DriverResponse.ACCEPTED:
            return JsonResponse({'error': 'You have already accepted this assignment.'}, status=409)
        
        now = timezone.now()
        reason = data.get('reason', '').strip()
        assignment.driver_response = Assignment.DriverResponse.DECLINED
        assignment.driver_responded_at = now
        assignment.cancellation_reason = reason or 'Declined by driver'
        assignment.save(update_fields=['driver_response', 'driver_responded_at', 'cancellation_reason', 'updated_at'])

        # try to dispatch to next optimal driver
        _dispatch_to_next_optimal_drivers(assignment.request)

        return JsonResponse({'success': True, 'status': assignment.request.status})

    except DriverStatus.DoesNotExist:
        return JsonResponse({'error': 'Driver status not found'}, status=404)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
        
@login_required
@require_POST
def complete_driver_assignment(request):
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Only drivers can complete jobs'}, status=403)

    try:
        import json
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        notes = (data.get('notes') or '').strip()

        driver_status = DriverStatus.objects.get(user=request.user)
        assignment = _get_driver_assignment_for_action(driver_status, assignment_id)

        if assignment.request.status != 'IN-PROGRESS':
            return JsonResponse({'error': 'Only in-progress jobs can be completed.'}, status=409)

        now = timezone.now()
        start_time = assignment.accepted_at or assignment.driver_responded_at or assignment.offer_sent_at
        completion_minutes = max(0, int((now - start_time).total_seconds() // 60))

        assignment.completed_at = now
        assignment.save(update_fields=['completed_at', 'updated_at'])

        assignment.request.status = 'COMPLETED'
        assignment.request.save(update_fields=['status', 'updated_at'])

        driver_status.status = DriverStatus.Status.AVAILABLE
        driver_status.save(update_fields=['status', 'updated_at'])

        JobHistory.objects.update_or_create(
            request=assignment.request,
            defaults={
                'driver': driver_status,
                'assignment': assignment,
                'start_time': start_time,
                'end_time': now,
                'completion_time_minutes': completion_minutes,
                'driver_notes': notes or None,
            },
        )

        return JsonResponse({'success': True, 'status': assignment.request.status})
    except DriverStatus.DoesNotExist:
        return JsonResponse({'error': 'Driver status not found'}, status=404)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def cancel_driver_assignment(request):
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Only drivers can cancel jobs'}, status=403)

    try:
        import json
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        reason = (data.get('reason') or '').strip() or 'Cancelled by driver'

        driver_status = DriverStatus.objects.get(user=request.user)
        assignment = _get_driver_assignment_for_action(driver_status, assignment_id)

        if assignment.request.status != 'IN-PROGRESS':
            return JsonResponse({'error': 'Only in-progress jobs can be cancelled.'}, status=409)

        now = timezone.now()
        assignment.cancellation_reason = reason
        assignment.save(update_fields=['cancellation_reason', 'updated_at'])

        Assignment.objects.filter(request=assignment.request).exclude(id=assignment.id).filter(
            driver_responded_at__isnull=True,
            accepted_at__isnull=True,
        ).update(
            driver_response=Assignment.DriverResponse.DECLINED,
            driver_responded_at=now,
            cancellation_reason='Request cancelled by active driver',
            updated_at=now,
        )

        assignment.request.status = 'CANCELLED'
        assignment.request.save(update_fields=['status', 'updated_at'])

        driver_status.status = DriverStatus.Status.AVAILABLE
        driver_status.save(update_fields=['status', 'updated_at'])

        return JsonResponse({'success': True, 'status': assignment.request.status})
    except DriverStatus.DoesNotExist:
        return JsonResponse({'error': 'Driver status not found'}, status=404)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def request_driver_assistance(request):
    if request.user.role != 'DRIVER':
        return JsonResponse({'error': 'Only drivers can request assistance'}, status=403)

    try:
        import json
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        notes = (data.get('notes') or '').strip() or 'Driver requested assistance.'

        driver_status = DriverStatus.objects.get(user=request.user)
        assignment = _get_driver_assignment_for_action(driver_status, assignment_id)

        if assignment.request.status != 'IN-PROGRESS':
            return JsonResponse({'error': 'Assistance can only be requested for in-progress jobs.'}, status=409)

        now = timezone.now()
        assignment.assistance_requested_at = now
        assignment.assistance_notes = notes
        assignment.save(update_fields=['assistance_requested_at', 'assistance_notes', 'updated_at'])

        if assignment.request.priority != 'EMERGENCY':
            assignment.request.priority = 'EMERGENCY'
            assignment.request.save(update_fields=['priority', 'updated_at'])

        return JsonResponse({
            'success': True,
            'status': assignment.request.status,
            'priority': assignment.request.priority,
            'assistance_requested_at': now.isoformat(),
        })
    except DriverStatus.DoesNotExist:
        return JsonResponse({'error': 'Driver status not found'}, status=404)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
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
    recovery_request.status = 'IN-PROGRESS'
    recovery_request.save(update_fields=['status', 'updated_at'])
    driver.status = DriverStatus.Status.IN_PROGRESS
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
    if latest_assignment and latest_assignment.driver.status == DriverStatus.Status.IN_PROGRESS:
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

    import json as json_mod
    from django.db.models import Count, Avg
    from django.db.models.functions import TruncDate

    total_requests = RecoveryRequest.objects.count()
    completed = RecoveryRequest.objects.filter(status='COMPLETED').count()
    cancelled = RecoveryRequest.objects.filter(status='CANCELLED').count()
    pending = RecoveryRequest.objects.filter(status='PENDING').count()
    in_progress = RecoveryRequest.objects.filter(status='IN-PROGRESS').count()

    avg_completion = JobHistory.objects.aggregate(
        avg=Avg('completion_time_minutes')
    )['avg']

    total_drivers = User.objects.filter(role='DRIVER', status='APPROVED').count()
    total_members = User.objects.filter(role='MEMBER', status='APPROVED').count()
    online_drivers = DriverStatus.objects.filter(status='AVAILABLE').count()

    requests_by_service = RecoveryRequest.objects.values(
        'service__name'
    ).annotate(count=Count('id')).order_by('-count')

    top_drivers = JobHistory.objects.values(
        'driver__user__username'
    ).annotate(
        jobs=Count('id'),
        avg_time=Avg('completion_time_minutes'),
    ).order_by('-jobs')[:5]

    # Requests per day for last 14 days
    fourteen_days_ago = timezone.now() - timedelta(days=13)
    daily_requests = (
        RecoveryRequest.objects
        .filter(created_at__date__gte=fourteen_days_ago.date())
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(
            total=Count('id'),
            completed_count=Count('id', filter=models.Q(status='COMPLETED')),
            cancelled_count=Count('id', filter=models.Q(status='CANCELLED')),
        )
        .order_by('day')
    )
    # Build full 14-day series (fill gaps with zeros)
    daily_map = {row['day']: row for row in daily_requests}
    chart_labels = []
    chart_total = []
    chart_completed = []
    chart_cancelled = []
    for i in range(14):
        day = (fourteen_days_ago + timedelta(days=i)).date()
        row = daily_map.get(day, {})
        chart_labels.append(day.strftime('%b %d'))
        chart_total.append(row.get('total', 0))
        chart_completed.append(row.get('completed_count', 0))
        chart_cancelled.append(row.get('cancelled_count', 0))

    # Driver performance: jobs + avg time for all drivers with history
    driver_performance = JobHistory.objects.values(
        'driver__user__username'
    ).annotate(
        jobs=Count('id'),
        avg_time=Avg('completion_time_minutes'),
    ).order_by('-jobs')[:10]

    driver_perf_names = [d['driver__user__username'] for d in driver_performance]
    driver_perf_jobs = [d['jobs'] for d in driver_performance]
    driver_perf_times = [round(d['avg_time'], 1) if d['avg_time'] else 0 for d in driver_performance]

    return render(request, 'usermanagement/admin_analytics.html', {
        'total_requests': total_requests,
        'completed': completed,
        'cancelled': cancelled,
        'pending': pending,
        'in_progress': in_progress,
        'avg_completion': round(avg_completion, 1) if avg_completion else 0,
        'total_drivers': total_drivers,
        'total_members': total_members,
        'online_drivers': online_drivers,
        'requests_by_service': requests_by_service,
        'top_drivers': top_drivers,
        'chart_labels_json': json_mod.dumps(chart_labels),
        'chart_total_json': json_mod.dumps(chart_total),
        'chart_completed_json': json_mod.dumps(chart_completed),
        'chart_cancelled_json': json_mod.dumps(chart_cancelled),
        'driver_perf_names_json': json_mod.dumps(driver_perf_names),
        'driver_perf_jobs_json': json_mod.dumps(driver_perf_jobs),
        'driver_perf_times_json': json_mod.dumps(driver_perf_times),
    })

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

            selected_count = _dispatch_to_next_optimal_drivers(recovery_request)

            if selected_count:
                messages.success(
                    request,
                    f'Recovery request submitted. Sent to {selected_count} optimal driver(s). Drivers must accept within 60 seconds.'
                )
            else:
                messages.success(
                    request,
                    'Recovery request submitted. No matching nearby driver is available right now.'
                )

            return redirect('dashboard')
        except Exception as e:
            return render_form(f'Could not save your request: {e}')

    return redirect('dashboard')