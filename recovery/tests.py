"""Tests for recovery models: RecoveryRequest, Assignment, JobHistory."""
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from recovery.models import Assignment, JobHistory, RecoveryRequest
from services.models import Service
from usermanagement.models import DriverStatus, User


class RecoveryBaseTestCase(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username='m1', email='m1@t.com', password='pw', role='MEMBER', status='APPROVED')
        self.driver_user = User.objects.create_user(
            username='d1', email='d1@t.com', password='pw', role='DRIVER', status='APPROVED')
        self.service = Service.objects.create(
            name='Towing', description='d', price='10', estimated_duration='30',
        )
        self.driver_status = DriverStatus.objects.create(
            user=self.driver_user, status='AVAILABLE', license_number='L',
            vehicle_type='TOW_TRUCK', vehicle_registration='X',
            qualification=[], specialization=[self.service.id],
        )

    def _request(self, **kwargs):
        defaults = dict(
            member=self.member, service=self.service,
            location_latitude=Decimal('53.48'), location_longitude=Decimal('-2.24'),
            address='1 High St', issue_description='flat',
            vehicle_details='AB12 CDE',
        )
        defaults.update(kwargs)
        return RecoveryRequest.objects.create(**defaults)


class TestRecoveryRequest(RecoveryBaseTestCase):
    def test_RR01_create(self):
        rr = self._request()
        self.assertEqual(rr.status, 'PENDING')

    def test_RR02_default_priority(self):
        rr = self._request()
        self.assertEqual(rr.priority, 'NORMAL')

    def test_RR03_valid_statuses(self):
        for s in ['PENDING', 'ASSIGNED', 'IN-PROGRESS', 'COMPLETED', 'CANCELLED']:
            rr = self._request(status=s)
            rr.full_clean()

    def test_RR04_place_values(self):
        for p in ['MOTORWAY', 'ROAD', 'NEAR HOUSE']:
            rr = self._request(place=p)
            rr.full_clean()

    def test_RR05_fk_member(self):
        rr = self._request()
        self.assertEqual(rr.member, self.member)

    def test_RR06_fk_service(self):
        rr = self._request()
        self.assertEqual(rr.service, self.service)


class TestAssignment(RecoveryBaseTestCase):
    def test_AS01_create(self):
        rr = self._request()
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now(), driver_response='TIMEOUT',
        )
        self.assertIsNotNone(a.id)

    def test_AS02_valid_driver_responses(self):
        rr = self._request()
        for resp in ['ACCEPTED', 'DECLINED', 'TIMEOUT']:
            a = Assignment.objects.create(
                request=rr, driver=self.driver_status,
                offer_sent_at=timezone.now(), driver_response=resp,
            )
            a.full_clean()

    def test_AS03_multiple_per_request(self):
        rr = self._request()
        u2 = User.objects.create_user(username='d2', email='d2@t.com', password='p',
                                      role='DRIVER', status='APPROVED')
        ds2 = DriverStatus.objects.create(
            user=u2, status='AVAILABLE', license_number='L',
            vehicle_type='TOW_TRUCK', vehicle_registration='X',
            qualification=[], specialization=[self.service.id],
        )
        Assignment.objects.create(request=rr, driver=self.driver_status,
                                  offer_sent_at=timezone.now(), driver_response='TIMEOUT')
        Assignment.objects.create(request=rr, driver=ds2,
                                  offer_sent_at=timezone.now(), driver_response='TIMEOUT')
        self.assertEqual(rr.assignments.count(), 2)

    def test_AS04_accepted_timestamp(self):
        rr = self._request()
        now = timezone.now()
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=now, driver_response='ACCEPTED', accepted_at=now,
        )
        self.assertEqual(a.accepted_at, now)

    def test_AS05_cancellation_reason(self):
        rr = self._request()
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now(), driver_response='DECLINED',
            cancellation_reason='driver busy',
        )
        self.assertEqual(a.cancellation_reason, 'driver busy')


class TestJobHistory(RecoveryBaseTestCase):
    def _accepted(self):
        rr = self._request(status='COMPLETED')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now(), driver_response='ACCEPTED',
            accepted_at=timezone.now(),
        )
        return rr, a

    def test_JH01_create(self):
        rr, a = self._accepted()
        start = timezone.now() - timedelta(minutes=45)
        end = timezone.now()
        jh = JobHistory.objects.create(
            request=rr, driver=self.driver_status, assignment=a,
            start_time=start, end_time=end, completion_time_minutes=45,
        )
        self.assertEqual(jh.completion_time_minutes, 45)

    def test_JH02_one_to_one_request(self):
        rr, a = self._accepted()
        now = timezone.now()
        JobHistory.objects.create(
            request=rr, driver=self.driver_status, assignment=a,
            start_time=now, end_time=now, completion_time_minutes=0,
        )
        u2 = User.objects.create_user(username='d9', email='d9@t.com', password='p',
                                      role='DRIVER', status='APPROVED')
        ds2 = DriverStatus.objects.create(
            user=u2, status='AVAILABLE', license_number='L',
            vehicle_type='TOW_TRUCK', vehicle_registration='X',
            qualification=[], specialization=[],
        )
        a2 = Assignment.objects.create(
            request=rr, driver=ds2, offer_sent_at=now, driver_response='DECLINED',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                JobHistory.objects.create(
                    request=rr, driver=ds2, assignment=a2,
                    start_time=now, end_time=now, completion_time_minutes=0,
                )

    def test_JH03_completion_time(self):
        rr, a = self._accepted()
        start = timezone.now() - timedelta(minutes=45)
        end = timezone.now()
        jh = JobHistory.objects.create(
            request=rr, driver=self.driver_status, assignment=a,
            start_time=start, end_time=end, completion_time_minutes=45,
        )
        self.assertEqual(jh.completion_time_minutes, 45)

    def test_JH04_optional_rating(self):
        rr, a = self._accepted()
        now = timezone.now()
        jh = JobHistory.objects.create(
            request=rr, driver=self.driver_status, assignment=a,
            start_time=now, end_time=now, completion_time_minutes=0,
            member_rating=None,
        )
        self.assertIsNone(jh.member_rating)
