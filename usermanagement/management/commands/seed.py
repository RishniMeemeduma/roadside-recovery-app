from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from usermanagement.models import UserProfile, DriverStatus
from services.models import Service
from recovery.models import RecoveryRequest, Assignment, JobHistory, DriverLocation


class Command(BaseCommand):
    help = 'Seed database with sample users, services, requests, driver status, assignments'

    def handle(self, *args, **options):
        User = get_user_model()

        self.stdout.write('Seeding database...')

        # Admin user
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'role': 'ADMIN',
                'is_staff': True,
                'is_superuser': True,
                'active': True,
            },
        )
        if created:
            admin.set_password('admin123')
            admin.save()
            self.stdout.write('- created admin')

        # Member user
        member, created = User.objects.get_or_create(
            username='member1',
            defaults={
                'email': 'member1@example.com',
                'role': 'MEMBER',
                'active': True,
            },
        )
        if created:
            member.set_password('member123')
            member.save()
            self.stdout.write('- created member1')

        UserProfile.objects.get_or_create(
            user=member,
            defaults={
                'first_name': 'Member',
                'last_name': 'One',
                'phone': '0800000001',
                'address': '123 Member St',
                'membership_tier': 'STANDARD',
            },
        )

        # Driver user
        driver_user, created = User.objects.get_or_create(
            username='driver1',
            defaults={
                'email': 'driver1@example.com',
                'role': 'DRIVER',
                'active': True,
            },
        )
        if created:
            driver_user.set_password('driver123')
            driver_user.save()
            self.stdout.write('- created driver1')

        DriverStatus.objects.get_or_create(
            user=driver_user,
            defaults={
                'status': 'AVAILABLE',
                'license_number': 'DL-001',
                'vehicle_type': 'TOW_TRUCK',
                'vehicle_registration': 'ABC-1234',
                'qualification': ['Towing'],
                'specialization': ['Flat tyre', 'Battery'],
                'acceptance_rate': 95,
            },
        )

        # Service seed
        services = [
            {'name': 'Member Assist', 'description': 'Member-specific recovery', 'price': '25.00', 'estimated_duration': '30m'},
            {'name': 'Driver Assist', 'description': 'Driver dispatch support', 'price': '30.00', 'estimated_duration': '40m'},
            {'name': 'Towing', 'description': 'Vehicle towing', 'price': '50.00', 'estimated_duration': '1h'},
        ]

        for svc in services:
            svc_obj, _ = Service.objects.get_or_create(name=svc['name'], defaults=svc)

        member_service = Service.objects.get(name='Member Assist')

        # Recovery request
        req, created = RecoveryRequest.objects.get_or_create(
            member=member,
            service=member_service,
            location_latitude=12.9716,
            location_longitude=77.5946,
            issue_description='Engine stalled',
            vehicle_details='Sedan',
            defaults={
                'status': 'PENDING',
                'priority': 'NORMAL',
                'place': 'ROAD',
                'address': 'MemberLocation, City',
            },
        )

        if created:
            self.stdout.write('- created recovery request')

        # Assignment +JobHistory if none exists
        assignment, created = Assignment.objects.get_or_create(
            request=req,
            driver=DriverStatus.objects.get(user=driver_user),
            defaults={
                'offer_sent_at': timezone.now(),
                'driver_response': 'ACCEPTED',
            },
        )

        if created:
            JobHistory.objects.get_or_create(
                request=req,
                driver=DriverStatus.objects.get(user=driver_user),
                assignment=assignment,
                defaults={
                    'start_time': timezone.now(),
                    'end_time': timezone.now(),
                    'completion_time_minutes': 45,
                    'member_rating': 5,
                    'driver_notes': 'Fast response',
                },
            )
            self.stdout.write('- created assignment + job history')

        self.stdout.write(self.style.SUCCESS('Seeding complete'))
