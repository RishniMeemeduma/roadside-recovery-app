"""Tests for usermanagement: models, helpers, auth, and driver/admin API endpoints."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from usermanagement.models import DriverLocation, DriverStatus, User, UserProfile
from usermanagement import views as um_views
from recovery.models import Assignment, RecoveryRequest, JobHistory
from services.models import Service


class BaseTestCase(TestCase):
    """Shared fixtures per testing plan §7."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin1', email='admin@test.com',
            password='testpass123', role='ADMIN', status='APPROVED',
        )
        self.member = User.objects.create_user(
            username='member1', email='member@test.com',
            password='testpass123', role='MEMBER', status='APPROVED',
        )
        UserProfile.objects.create(user=self.member, first_name='Mem', last_name='Ber', phone='0123')

        self.driver_user = User.objects.create_user(
            username='driver1', email='driver@test.com',
            password='testpass123', role='DRIVER', status='APPROVED',
        )
        UserProfile.objects.create(user=self.driver_user, first_name='Dri', last_name='Ver', phone='0456')

        self.service = Service.objects.create(
            name='Towing', description='Vehicle towing',
            price='49.99', estimated_duration='45 min',
        )

        self.driver_status = DriverStatus.objects.create(
            user=self.driver_user,
            status='AVAILABLE',
            license_number='DRV123',
            vehicle_type='TOW_TRUCK',
            vehicle_registration='AB12 CDE',
            qualification=['MOT'],
            specialization=[self.service.id],
        )
        self.driver_location = DriverLocation.objects.create(
            driver=self.driver_user,
            latitude=Decimal('53.480800'),
            longitude=Decimal('-2.242600'),
            is_current=True,
        )

    def _make_request(self, *, member=None, service=None, lat='53.483959', lon='-2.244644',
                      status='PENDING', priority='NORMAL', place='ROAD'):
        return RecoveryRequest.objects.create(
            member=member or self.member,
            service=service or self.service,
            location_latitude=Decimal(lat),
            location_longitude=Decimal(lon),
            address='1 Test St',
            issue_description='flat tyre',
            vehicle_details='AB12 CDE',
            status=status,
            priority=priority,
            place=place,
        )


# ---------------------------------------------------------------------------
# 2.1 User model
# ---------------------------------------------------------------------------
class TestUserModel(BaseTestCase):
    def test_UM01_create_member(self):
        u = User.objects.create_user(username='m2', email='m2@t.com', password='p', role='MEMBER')
        self.assertEqual(u.role, 'MEMBER')
        self.assertEqual(u.status, 'PENDING')
        self.assertTrue(u.active)

    def test_UM02_create_driver(self):
        u = User.objects.create_user(username='d2', email='d2@t.com', password='p', role='DRIVER')
        self.assertEqual(u.role, 'DRIVER')
        self.assertEqual(u.status, 'PENDING')

    def test_UM03_create_admin(self):
        u = User.objects.create_user(username='a2', email='a2@t.com', password='p', role='ADMIN')
        self.assertEqual(u.role, 'ADMIN')

    def test_UM04_email_unique(self):
        with self.assertRaises(IntegrityError):
            User.objects.create_user(username='dup', email='member@test.com', password='p', role='MEMBER')

    def test_UM05_uuid_primary_key(self):
        u = User.objects.create_user(username='uid', email='uid@t.com', password='p', role='MEMBER')
        self.assertIsInstance(u.uuid, uuid.UUID)

    def test_UM06_soft_delete(self):
        now = timezone.now()
        self.member.active = False
        self.member.deleted_at = now
        self.member.save()
        refreshed = User.objects.get(pk=self.member.pk)
        self.assertFalse(refreshed.active)
        self.assertIsNotNone(refreshed.deleted_at)

    def test_UM07_default_status_pending(self):
        u = User.objects.create_user(username='x', email='x@t.com', password='p', role='MEMBER')
        self.assertEqual(u.status, 'PENDING')


# ---------------------------------------------------------------------------
# 2.2 UserProfile
# ---------------------------------------------------------------------------
class TestUserProfile(BaseTestCase):
    def test_UP01_create_profile(self):
        self.assertEqual(self.member.profile.first_name, 'Mem')
        self.assertEqual(self.member.profile.phone, '0123')

    def test_UP02_default_tier(self):
        self.assertEqual(self.member.profile.membership_tier, 'STANDARD')

    def test_UP03_profile_reverse(self):
        self.assertIsInstance(self.member.profile, UserProfile)


# ---------------------------------------------------------------------------
# 2.3 DriverStatus
# ---------------------------------------------------------------------------
class TestDriverStatus(BaseTestCase):
    def test_DS01_create(self):
        self.assertEqual(self.driver_status.status, 'AVAILABLE')
        self.assertEqual(self.driver_status.license_number, 'DRV123')

    def test_DS02_valid_vehicle_types(self):
        for vt in ['MOBILE_UNIT', 'TOW_TRUCK', 'FLATBED']:
            u = User.objects.create_user(username=f'd_{vt}', email=f'{vt}@t.com', password='p', role='DRIVER')
            ds = DriverStatus.objects.create(
                user=u, license_number='L', vehicle_type=vt,
                vehicle_registration='X', qualification=[], specialization=[],
            )
            ds.full_clean()

    def test_DS03_invalid_vehicle_type(self):
        from django.core.exceptions import ValidationError
        u = User.objects.create_user(username='dx', email='dx@t.com', password='p', role='DRIVER')
        ds = DriverStatus(
            user=u, license_number='L', vehicle_type='HELICOPTER',
            vehicle_registration='X', qualification=[], specialization=[],
        )
        with self.assertRaises(ValidationError):
            ds.full_clean()

    def test_DS04_specialization_json(self):
        self.driver_status.specialization = [1, 2, 3]
        self.driver_status.save()
        self.assertEqual(DriverStatus.objects.get(pk=self.driver_status.pk).specialization, [1, 2, 3])

    def test_DS05_qualification_json(self):
        self.driver_status.qualification = ['MOT', 'HGV']
        self.driver_status.save()
        self.assertEqual(DriverStatus.objects.get(pk=self.driver_status.pk).qualification, ['MOT', 'HGV'])


# ---------------------------------------------------------------------------
# 2.4 DriverLocation
# ---------------------------------------------------------------------------
class TestDriverLocation(BaseTestCase):
    def test_DL01_create(self):
        self.assertTrue(self.driver_location.is_current)

    def test_DL02_multiple_locations(self):
        DriverLocation.objects.filter(driver=self.driver_user).update(is_current=False)
        DriverLocation.objects.create(
            driver=self.driver_user, latitude=Decimal('54.0'), longitude=Decimal('-2.5'), is_current=True,
        )
        self.assertEqual(DriverLocation.objects.filter(driver=self.driver_user).count(), 2)
        self.assertEqual(DriverLocation.objects.filter(driver=self.driver_user, is_current=True).count(), 1)

    def test_DL03_precision(self):
        loc = DriverLocation.objects.create(
            driver=self.driver_user,
            latitude=Decimal('53.483959'), longitude=Decimal('-2.244644'),
        )
        self.assertEqual(loc.latitude, Decimal('53.483959'))


# ---------------------------------------------------------------------------
# 3.1 Haversine
# ---------------------------------------------------------------------------
class TestHaversine(TestCase):
    def test_HV01_manchester_liverpool(self):
        d = um_views._haversine_km(53.4808, -2.2426, 53.4084, -2.9916)
        self.assertAlmostEqual(d, 50, delta=5)

    def test_HV02_same_point(self):
        self.assertEqual(um_views._haversine_km(0, 0, 0, 0), 0)

    def test_HV03_antipodal(self):
        d = um_views._haversine_km(0, 0, 0, 180)
        self.assertAlmostEqual(d, 20015, delta=50)


# ---------------------------------------------------------------------------
# 3.2 Service matching
# ---------------------------------------------------------------------------
class TestSupportsService(BaseTestCase):
    def test_SM01_supports_by_id(self):
        self.driver_status.specialization = [self.service.id]
        self.assertTrue(um_views._supports_service(self.driver_status, self.service))

    def test_SM02_no_match(self):
        self.driver_status.specialization = [99999]
        self.assertFalse(um_views._supports_service(self.driver_status, self.service))

    def test_SM03_empty(self):
        self.driver_status.specialization = []
        self.assertFalse(um_views._supports_service(self.driver_status, self.service))

    def test_SM04_supports_by_name(self):
        self.driver_status.specialization = ['Towing']
        self.assertTrue(um_views._supports_service(self.driver_status, self.service))


# ---------------------------------------------------------------------------
# 3.3 Driver ranking
# ---------------------------------------------------------------------------
class TestRankDrivers(BaseTestCase):
    def _make_driver(self, username, lat, lon, status='AVAILABLE', approved=True, location=True, spec=None):
        u = User.objects.create_user(
            username=username, email=f'{username}@t.com', password='p',
            role='DRIVER', status='APPROVED' if approved else 'PENDING',
        )
        ds = DriverStatus.objects.create(
            user=u, status=status, license_number='L', vehicle_type='TOW_TRUCK',
            vehicle_registration='X', qualification=[], specialization=spec if spec is not None else [self.service.id],
        )
        if location:
            DriverLocation.objects.create(
                driver=u, latitude=Decimal(str(lat)), longitude=Decimal(str(lon)), is_current=True,
            )
        return ds

    def test_DR01_rank_by_distance(self):
        rr = self._make_request(lat='53.0', lon='-2.0')
        # default driver is far
        DriverLocation.objects.filter(driver=self.driver_user).update(is_current=False)
        close = self._make_driver('close', 53.01, -2.01)
        far = self._make_driver('far', 54.0, -3.0)
        ranked = um_views._rank_optimal_drivers(rr)
        ids = [d.id for _, d in ranked]
        self.assertEqual(ids[0], close.id)
        self.assertIn(far.id, ids)

    def test_DR02_exclude_offline(self):
        rr = self._make_request()
        self._make_driver('offline1', 53.5, -2.2, status='OFFLINE')
        ranked = um_views._rank_optimal_drivers(rr)
        offline_ids = [d.user.username for _, d in ranked if d.user.username == 'offline1']
        self.assertEqual(offline_ids, [])

    def test_DR03_exclude_no_location(self):
        rr = self._make_request()
        DriverLocation.objects.filter(driver=self.driver_user).update(is_current=False)
        self._make_driver('nl', 53.5, -2.2, location=False)
        ranked = um_views._rank_optimal_drivers(rr)
        self.assertEqual(ranked, [])

    def test_DR04_exclude_already_offered(self):
        rr = self._make_request()
        ranked = um_views._rank_optimal_drivers(rr, excluded_driver_ids={self.driver_status.id})
        self.assertEqual(ranked, [])

    def test_DR05_specialist_outranks_nearer_non_specialist(self):
        # FR-0006: 0.6·specialisation dominates 0.4·proximity, so a specialist
        # even at the distance cap outranks a non-specialist at the request
        # location. Specialist score 0.6·0 + 0.6 = 0.60; non-specialist score
        # 0.4·1 + 0 = 0.40.
        rr = self._make_request(lat='53.0', lon='-2.0')
        DriverLocation.objects.filter(driver=self.driver_user).update(is_current=False)
        far_specialist = self._make_driver('far_spec', 53.3, -2.0, spec=[self.service.id])
        near_generalist = self._make_driver('near_gen', 53.001, -2.001, spec=[])
        ranked = um_views._rank_optimal_drivers(rr)
        ids = [d.id for _, d in ranked]
        self.assertEqual(ids[0], far_specialist.id)
        self.assertIn(near_generalist.id, ids)

    def test_DR06_non_specialists_now_eligible(self):
        # Previously non-specialists were excluded entirely. With the weighted
        # score they remain eligible so a request doesn't stall when no
        # specialist is available.
        rr = self._make_request()
        DriverLocation.objects.filter(driver=self.driver_user).update(is_current=False)
        generalist = self._make_driver('gen_only', 53.5, -2.2, spec=[])
        ranked = um_views._rank_optimal_drivers(rr)
        ids = [d.id for _, d in ranked]
        self.assertIn(generalist.id, ids)


# ---------------------------------------------------------------------------
# 3.4 Dispatch logic
# ---------------------------------------------------------------------------
class TestDispatch(BaseTestCase):
    def test_DP01_batch_size(self):
        rr = self._make_request()
        # 4 more available drivers (total 5)
        for i in range(4):
            u = User.objects.create_user(username=f'd{i}', email=f'd{i}@t.com', password='p',
                                         role='DRIVER', status='APPROVED')
            DriverStatus.objects.create(
                user=u, status='AVAILABLE', license_number='L', vehicle_type='TOW_TRUCK',
                vehicle_registration='X', qualification=[], specialization=[self.service.id],
            )
            DriverLocation.objects.create(driver=u, latitude=Decimal('53.5'), longitude=Decimal('-2.2'), is_current=True)
        count = um_views._dispatch_to_next_optimal_drivers(rr)
        self.assertEqual(count, 3)
        self.assertEqual(Assignment.objects.filter(request=rr).count(), 3)

    def test_DP02_no_available(self):
        self.driver_status.status = 'OFFLINE'
        self.driver_status.save()
        rr = self._make_request()
        count = um_views._dispatch_to_next_optimal_drivers(rr)
        self.assertEqual(count, 0)
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'PENDING')

    def test_DP03_fewer_than_batch(self):
        rr = self._make_request()
        count = um_views._dispatch_to_next_optimal_drivers(rr)
        self.assertEqual(count, 1)
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'ASSIGNED')

    def test_DP04_escalates_to_admin_after_max_batches(self):
        # FR-0006: once MAX_DISPATCH_BATCHES * DISPATCH_BATCH_SIZE offers have
        # been sent with no acceptance, further dispatch is capped and every
        # active admin gets an email.
        from django.core import mail
        User.objects.create_user(
            username='ops_admin', email='ops@quickassist.test',
            password='p', role='ADMIN', status='APPROVED',
        )
        rr = self._make_request()
        # Pre-seed 9 TIMEOUT offers from disposable driver accounts.
        for i in range(um_views.MAX_DISPATCH_BATCHES * um_views.DISPATCH_BATCH_SIZE):
            u = User.objects.create_user(
                username=f'exhausted_{i}', email=f'ex{i}@t.com', password='p',
                role='DRIVER', status='APPROVED',
            )
            ds = DriverStatus.objects.create(
                user=u, status='AVAILABLE', license_number='L',
                vehicle_type='TOW_TRUCK', vehicle_registration='X',
                qualification=[], specialization=[self.service.id],
            )
            Assignment.objects.create(
                request=rr, driver=ds, offer_sent_at=timezone.now(),
                driver_response=Assignment.DriverResponse.TIMEOUT,
            )
        mail.outbox = []
        count = um_views._dispatch_to_next_optimal_drivers(rr)
        self.assertEqual(count, 0)
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'PENDING')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ops@quickassist.test', mail.outbox[0].to)
        self.assertIn(str(rr.id), mail.outbox[0].subject)

    def test_DP05_escalates_when_no_eligible_drivers(self):
        # When _rank_optimal_drivers returns empty (every driver offline or
        # excluded), escalation fires immediately instead of looping forever.
        from django.core import mail
        User.objects.create_user(
            username='ops2', email='ops2@quickassist.test',
            password='p', role='ADMIN', status='APPROVED',
        )
        self.driver_status.status = 'OFFLINE'
        self.driver_status.save()
        rr = self._make_request()
        mail.outbox = []
        count = um_views._dispatch_to_next_optimal_drivers(rr)
        self.assertEqual(count, 0)
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'PENDING')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ops2@quickassist.test', mail.outbox[0].to)


# ---------------------------------------------------------------------------
# 3.5 Offer rotation
# ---------------------------------------------------------------------------
class TestRotation(BaseTestCase):
    def test_OR01_unexpired(self):
        rr = self._make_request(status='ASSIGNED')
        Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now() - timedelta(seconds=30),
            driver_response=Assignment.DriverResponse.TIMEOUT,
        )
        self.assertEqual(um_views._rotate_expired_dispatch_offers(rr), 0)

    def test_OR02_expired_rotates(self):
        rr = self._make_request(status='ASSIGNED')
        Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now() - timedelta(seconds=61),
            driver_response=Assignment.DriverResponse.TIMEOUT,
        )
        um_views._rotate_expired_dispatch_offers(rr)
        a = Assignment.objects.get(request=rr, driver=self.driver_status)
        self.assertEqual(a.driver_response, 'TIMEOUT')
        self.assertIsNotNone(a.driver_responded_at)

    def test_OR03_already_accepted_no_rotation(self):
        rr = self._make_request(status='ASSIGNED')
        Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now() - timedelta(seconds=120),
            driver_response=Assignment.DriverResponse.ACCEPTED,
            accepted_at=timezone.now(),
        )
        self.assertEqual(um_views._rotate_expired_dispatch_offers(rr), 0)

    def test_OR04_no_pending_triggers_dispatch(self):
        rr = self._make_request(status='ASSIGNED')
        # No pending offers; there is an available driver -> new dispatch
        count = um_views._rotate_expired_dispatch_offers(rr)
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------
# 4.1 Authentication
# ---------------------------------------------------------------------------
class TestAuthentication(BaseTestCase):
    def test_AU01_signup_member(self):
        r = self.client.post('/signup/', {
            'username': 'newm', 'email': 'newm@t.com', 'password': 'pw',
            'confirm_password': 'pw', 'first_name': 'N', 'last_name': 'M',
            'phone': '111', 'role': 'MEMBER', 'address': 'x',
        })
        self.assertTrue(User.objects.filter(username='newm').exists())
        self.assertEqual(r.status_code, 302)

    def test_AU02_signup_driver(self):
        r = self.client.post('/signup/', {
            'username': 'newd', 'email': 'newd@t.com', 'password': 'pw',
            'confirm_password': 'pw', 'first_name': 'N', 'last_name': 'D',
            'phone': '111', 'role': 'DRIVER', 'address': 'x',
            'license_number': 'LIC', 'vehicle_type': 'TOW_TRUCK',
            'vehicle_registration': 'REG1', 'qualification': 'MOT',
            'specialization': [str(self.service.id)],
        })
        u = User.objects.filter(username='newd').first()
        self.assertIsNotNone(u)
        self.assertTrue(DriverStatus.objects.filter(user=u).exists())

    def test_AU03_signup_duplicate_email(self):
        self.client.post('/signup/', {
            'username': 'dup1', 'email': 'member@test.com', 'password': 'pw',
            'confirm_password': 'pw', 'role': 'MEMBER',
        })
        self.assertFalse(User.objects.filter(username='dup1').exists())

    def test_AU04_login_valid(self):
        ok = self.client.login(username='member1', password='testpass123')
        self.assertTrue(ok)

    def test_AU05_login_invalid(self):
        ok = self.client.login(username='member1', password='WRONG')
        self.assertFalse(ok)

    def test_AU07_logout(self):
        self.client.login(username='member1', password='testpass123')
        r = self.client.get('/logout/')
        self.assertEqual(r.status_code, 302)

    def test_AU08_dashboard_redirect(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r.url)

    def test_AU09_recaptcha_blocks_login_when_token_fails(self):
        # FR-0002: when reCAPTCHA is configured and verification fails, the
        # login POST must not reach authenticate().
        from unittest.mock import patch
        from usermanagement import views as um_views
        with self.settings(RECAPTCHA_SECRET_KEY='dummy-secret'):
            with patch.object(um_views, '_verify_recaptcha', return_value=False) as m:
                r = self.client.post('/login/', {
                    'username': 'member1', 'password': 'testpass123',
                    'g-recaptcha-response': 'invalid',
                })
                self.assertTrue(m.called, 'reCAPTCHA verifier was not invoked')
                self.assertEqual(r.status_code, 200)
                self.assertFalse(r.wsgi_request.user.is_authenticated)

    def test_AU10_recaptcha_passes_login_when_token_valid(self):
        from unittest.mock import patch
        with self.settings(RECAPTCHA_SECRET_KEY='dummy-secret'):
            with patch('usermanagement.views._verify_recaptcha', return_value=True):
                r = self.client.post('/login/', {
                    'username': 'member1', 'password': 'testpass123',
                    'g-recaptcha-response': 'valid',
                })
                self.assertEqual(r.status_code, 302)

    def test_AU11_recaptcha_noop_when_secret_empty(self):
        # With no RECAPTCHA_SECRET_KEY configured, the gate is a no-op so dev
        # without keys still works.
        with self.settings(RECAPTCHA_SECRET_KEY=''):
            r = self.client.post('/login/', {
                'username': 'member1', 'password': 'testpass123',
            })
            self.assertEqual(r.status_code, 302)


# ---------------------------------------------------------------------------
# 4.2 Member dashboard & requests
# ---------------------------------------------------------------------------
class TestMemberWorkflow(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='member1', password='testpass123')

    def test_MR01_view_dashboard(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 200)

    def test_MR02_submit_valid(self):
        r = self.client.post('/submit-request/', {
            'service_id': self.service.id,
            'vehicle_registration': 'AB12 CDE',
            'vehicle_details': 'Ford Focus',
            'place': 'ROAD', 'details': 'flat tyre', 'address': '1 High St',
            'latitude': '53.48', 'longitude': '-2.24',
        })
        self.assertEqual(r.status_code, 302)
        rr = RecoveryRequest.objects.get(member=self.member)
        self.assertIn(rr.status, ['ASSIGNED', 'PENDING'])

    def test_MR03_submit_without_service(self):
        r = self.client.post('/submit-request/', {
            'vehicle_registration': 'AB', 'vehicle_details': 'F', 'details': 'x',
            'address': 'a', 'latitude': '0', 'longitude': '0',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(RecoveryRequest.objects.exists())

    def test_MR04_submit_without_address(self):
        r = self.client.post('/submit-request/', {
            'service_id': self.service.id,
            'vehicle_registration': 'AB', 'vehicle_details': 'F', 'details': 'x',
            'address': '', 'latitude': '0', 'longitude': '0',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(RecoveryRequest.objects.exists())

    def test_MR05_cancel_pending(self):
        rr = self._make_request()
        r = self.client.post(f'/cancel-request/{rr.id}/')
        self.assertEqual(r.status_code, 302)
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'CANCELLED')

    def test_MR06_cancel_completed_fails(self):
        rr = self._make_request(status='COMPLETED')
        self.client.post(f'/cancel-request/{rr.id}/')
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'COMPLETED')

    def test_MR07_cancel_other_users_request(self):
        other = User.objects.create_user(username='m9', email='m9@t.com', password='p', role='MEMBER', status='APPROVED')
        rr = self._make_request(member=other)
        r = self.client.post(f'/cancel-request/{rr.id}/')
        self.assertEqual(r.status_code, 404)

    def test_MR08_member_requests_status_api(self):
        self._make_request()
        r = self.client.get('/api/member-requests-status/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('statuses', r.json())

    def test_MR09_driver_location_api(self):
        rr = self._make_request(status='ASSIGNED')
        Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now(),
            driver_response='ACCEPTED', accepted_at=timezone.now(),
        )
        r = self.client.get(f'/api/member-request-driver-location/{rr.id}/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['available'])
        self.assertEqual(data['driver_name'], 'driver1')

    def test_MR10_dvla_no_api_key(self):
        with self.settings(DVLA_API_KEY=''):
            r = self.client.post('/lookup-vehicle/', {'registration': 'AB12CDE'})
            self.assertEqual(r.status_code, 503)


# ---------------------------------------------------------------------------
# 4.3 Driver workflow
# ---------------------------------------------------------------------------
class TestDriverWorkflow(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='driver1', password='testpass123')

    def _post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type='application/json')

    def test_DW01_view_dashboard(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 200)

    def test_DW02_go_online(self):
        self.driver_status.status = 'OFFLINE'
        self.driver_status.save()
        r = self._post_json('/api/update-driver-status/', {'status': 'AVAILABLE'})
        self.assertEqual(r.status_code, 200)
        self.driver_status.refresh_from_db()
        self.assertEqual(self.driver_status.status, 'AVAILABLE')

    def test_DW03_go_offline(self):
        r = self._post_json('/api/update-driver-status/', {'status': 'OFFLINE'})
        self.assertEqual(r.status_code, 200)

    def test_DW04_offline_with_active_job(self):
        rr = self._make_request(status='IN-PROGRESS')
        Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now(),
            driver_response='ACCEPTED', accepted_at=timezone.now(),
        )
        r = self._post_json('/api/update-driver-status/', {'status': 'OFFLINE'})
        self.assertEqual(r.status_code, 409)

    def test_DW05_accept_assignment(self):
        rr = self._make_request(status='ASSIGNED')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now(),
            driver_response='TIMEOUT',
        )
        r = self._post_json('/api/accept-driver-assignment/', {'assignment_id': a.id})
        self.assertEqual(r.status_code, 200)
        rr.refresh_from_db()
        self.driver_status.refresh_from_db()
        self.assertEqual(rr.status, 'IN-PROGRESS')
        self.assertEqual(self.driver_status.status, 'IN_PROGRESS')

    def test_DW06_accept_expired(self):
        rr = self._make_request(status='ASSIGNED')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now() - timedelta(seconds=120),
            driver_response='TIMEOUT',
        )
        r = self._post_json('/api/accept-driver-assignment/', {'assignment_id': a.id})
        self.assertEqual(r.status_code, 409)

    def test_DW07_decline(self):
        rr = self._make_request(status='ASSIGNED')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now(),
            driver_response='TIMEOUT',
        )
        r = self._post_json('/api/accept-driver-assignment/', {'assignment_id': a.id, 'action': 'decline'})
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.driver_response, 'DECLINED')

    def test_DW08_complete(self):
        rr = self._make_request(status='IN-PROGRESS')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now() - timedelta(minutes=30),
            driver_response='ACCEPTED', accepted_at=timezone.now() - timedelta(minutes=30),
        )
        r = self._post_json('/api/complete-driver-assignment/', {'assignment_id': a.id, 'notes': 'done'})
        self.assertEqual(r.status_code, 200)
        rr.refresh_from_db()
        self.driver_status.refresh_from_db()
        self.assertEqual(rr.status, 'COMPLETED')
        self.assertEqual(self.driver_status.status, 'AVAILABLE')
        self.assertTrue(JobHistory.objects.filter(request=rr).exists())

    def test_DW09_cancel(self):
        rr = self._make_request(status='IN-PROGRESS')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now(),
            driver_response='ACCEPTED', accepted_at=timezone.now(),
        )
        r = self._post_json('/api/cancel-driver-assignment/', {'assignment_id': a.id, 'reason': 'breakdown'})
        self.assertEqual(r.status_code, 200)
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'CANCELLED')

    def test_DW10_request_assistance(self):
        rr = self._make_request(status='IN-PROGRESS')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now(),
            driver_response='ACCEPTED', accepted_at=timezone.now(),
        )
        r = self._post_json('/api/request-driver-assistance/', {'assignment_id': a.id, 'notes': 'help'})
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db()
        self.assertIsNotNone(a.assistance_requested_at)
        rr.refresh_from_db()
        self.assertEqual(rr.priority, 'EMERGENCY')

    def test_DW11_assistance_emails_admins(self):
        # FR-0007: requesting assistance notifies every active admin.
        from django.core import mail
        User.objects.create_user(
            username='admin_alpha', email='alpha@ops.test', password='p',
            role='ADMIN', status='APPROVED',
        )
        User.objects.create_user(
            username='admin_beta', email='beta@ops.test', password='p',
            role='ADMIN', status='APPROVED',
        )
        rr = self._make_request(status='IN-PROGRESS')
        a = Assignment.objects.create(
            request=rr, driver=self.driver_status, offer_sent_at=timezone.now(),
            driver_response='ACCEPTED', accepted_at=timezone.now(),
        )
        mail.outbox = []
        r = self._post_json(
            '/api/request-driver-assistance/',
            {'assignment_id': a.id, 'notes': 'stuck in ditch, need winch'},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn('alpha@ops.test', message.to)
        self.assertIn('beta@ops.test', message.to)
        self.assertIn(str(rr.id), message.subject)
        self.assertIn('stuck in ditch, need winch', message.body)

    def test_DW11_update_location(self):
        r = self._post_json('/api/update-location/', {'latitude': 53.5, 'longitude': -2.3})
        self.assertEqual(r.status_code, 200)
        current = DriverLocation.objects.filter(driver=self.driver_user, is_current=True)
        self.assertEqual(current.count(), 1)
        self.assertAlmostEqual(float(current.first().latitude), 53.5, places=4)

    def test_DW12_snapshot(self):
        r = self.client.get('/api/driver-assignment-snapshot/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('feed_version', data)
        self.assertIn('has_assignment', data)

    def test_DW13_dispatch_card_partial(self):
        r = self.client.get('/api/driver-dispatch-card/')
        self.assertEqual(r.status_code, 200)

    def test_DW14_non_driver_snapshot(self):
        self.client.logout()
        self.client.login(username='member1', password='testpass123')
        r = self.client.get('/api/driver-assignment-snapshot/')
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# 4.4 Admin operations
# ---------------------------------------------------------------------------
class TestAdminWorkflow(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='admin1', password='testpass123')

    def test_AD01_admin_dashboard(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 200)

    def test_AD02_recovery_requests_page(self):
        r = self.client.get('/dashboard/recovery-requests/')
        self.assertEqual(r.status_code, 200)

    def test_AD03_assign_request(self):
        rr = self._make_request()
        r = self.client.post(f'/dashboard/recovery-requests/{rr.id}/assign/',
                             {'driver_id': self.driver_status.id})
        self.assertEqual(r.status_code, 302)
        rr.refresh_from_db()
        self.driver_status.refresh_from_db()
        self.assertEqual(rr.status, 'IN-PROGRESS')
        self.assertEqual(self.driver_status.status, 'IN_PROGRESS')

    def test_AD04_assign_to_unavailable(self):
        self.driver_status.status = 'OFFLINE'
        self.driver_status.save()
        rr = self._make_request()
        r = self.client.post(f'/dashboard/recovery-requests/{rr.id}/assign/',
                             {'driver_id': self.driver_status.id})
        self.assertEqual(r.status_code, 404)

    def test_AD05_assign_non_pending(self):
        rr = self._make_request(status='IN-PROGRESS')
        r = self.client.post(f'/dashboard/recovery-requests/{rr.id}/assign/',
                             {'driver_id': self.driver_status.id})
        rr.refresh_from_db()
        # Must not double-assign
        self.assertEqual(rr.status, 'IN-PROGRESS')

    def test_AD06_decline_request(self):
        rr = self._make_request()
        r = self.client.post(f'/dashboard/recovery-requests/{rr.id}/decline/')
        self.assertEqual(r.status_code, 302)
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'CANCELLED')

    def test_AD07_create_user(self):
        self.client.post('/dashboard/create-user/', {
            'username': 'adminmade', 'email': 'am@t.com', 'password': 'pw',
            'role': 'MEMBER', 'first_name': 'A', 'last_name': 'M', 'phone': '999',
        })
        self.assertTrue(User.objects.filter(username='adminmade').exists())

    def test_AD08_create_driver(self):
        self.client.post('/dashboard/create-driver/', {
            'username': 'admindrv', 'email': 'ad@t.com', 'password': 'pw',
            'license_number': 'L', 'vehicle_type': 'TOW_TRUCK',
            'vehicle_registration': 'R', 'phone': '1',
        })
        u = User.objects.filter(username='admindrv').first()
        self.assertIsNotNone(u)
        self.assertTrue(DriverStatus.objects.filter(user=u).exists())

    def test_AD09_delete_user(self):
        victim = User.objects.create_user(
            username='victim', email='v@t.com', password='p', role='MEMBER', status='APPROVED')
        self.client.post(f'/dashboard/delete-user/{victim.uuid}/')
        # NB: admin_delete_user does hard-delete — adjust this test if soft-delete is implemented
        self.assertFalse(User.objects.filter(uuid=victim.uuid).exists())

    def test_AD10_approve_user(self):
        pending = User.objects.create_user(
            username='pend', email='p@t.com', password='p', role='MEMBER', status='PENDING')
        self.client.post(f'/dashboard/handle-request/{pending.uuid}/', {'action': 'accept'})
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'APPROVED')

    def test_AD11_reject_user(self):
        pending = User.objects.create_user(
            username='pend2', email='p2@t.com', password='p', role='MEMBER', status='PENDING')
        self.client.post(f'/dashboard/handle-request/{pending.uuid}/', {'action': 'decline'})
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'REJECTED')

    def test_AD12_services_page(self):
        r = self.client.get('/dashboard/services/')
        self.assertEqual(r.status_code, 200)

    def test_AD13_create_service(self):
        self.client.post('/dashboard/services/', {
            'action': 'create', 'name': 'Battery', 'description': 'b',
            'price': '10', 'estimated_duration': '15 min', 'active': 'on',
        })
        self.assertTrue(Service.objects.filter(name='Battery').exists())

    def test_AD14_delete_service(self):
        self.client.post(f'/dashboard/delete-service/{self.service.id}/')
        self.service.refresh_from_db()
        self.assertFalse(self.service.active)

    def test_AD15_analytics(self):
        r = self.client.get('/dashboard/analytics/')
        self.assertEqual(r.status_code, 200)

    def test_AD16_driver_locations_api(self):
        r = self.client.get('/api/driver-locations/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['drivers'][0]['name'], 'driver1')

    def test_AD17_requests_status_api(self):
        self._make_request()
        r = self.client.get('/api/admin-requests-status/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('requests', r.json())

    def test_AD18_non_admin_redirected(self):
        self.client.logout()
        self.client.login(username='member1', password='testpass123')
        r = self.client.get('/dashboard/recovery-requests/')
        self.assertEqual(r.status_code, 302)


# ---------------------------------------------------------------------------
# 4.5 Role-based access control
# ---------------------------------------------------------------------------
class TestRoleAccess(BaseTestCase):
    def test_AC01_member_cannot_access_admin_page(self):
        self.client.login(username='member1', password='testpass123')
        r = self.client.get('/dashboard/recovery-requests/')
        self.assertEqual(r.status_code, 302)

    def test_AC02_driver_cannot_access_admin_services(self):
        self.client.login(username='driver1', password='testpass123')
        r = self.client.get('/dashboard/services/')
        self.assertEqual(r.status_code, 302)

    def test_AC03_member_cannot_update_driver_status(self):
        self.client.login(username='member1', password='testpass123')
        r = self.client.post('/api/update-driver-status/',
                             data=json.dumps({'status': 'AVAILABLE'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_AC04_driver_cannot_access_member_api(self):
        self.client.login(username='driver1', password='testpass123')
        r = self.client.get('/api/member-requests-status/')
        self.assertEqual(r.status_code, 403)

    def test_AC05_admin_cannot_access_driver_snapshot(self):
        self.client.login(username='admin1', password='testpass123')
        r = self.client.get('/api/driver-assignment-snapshot/')
        self.assertEqual(r.status_code, 403)

    def test_AC06_unauth_redirect(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 302)


# ---------------------------------------------------------------------------
# 5. End-to-end flow tests
# ---------------------------------------------------------------------------
class TestE2EFlows(BaseTestCase):
    def test_E2E_full_lifecycle(self):
        # Member submits request
        self.client.login(username='member1', password='testpass123')
        self.client.post('/submit-request/', {
            'service_id': self.service.id,
            'vehicle_registration': 'AB12 CDE',
            'vehicle_details': 'Focus', 'place': 'ROAD',
            'details': 'flat', 'address': 'x',
            'latitude': '53.48', 'longitude': '-2.24',
        })
        rr = RecoveryRequest.objects.get(member=self.member)
        self.assertEqual(rr.status, 'ASSIGNED')
        a = Assignment.objects.get(request=rr, driver=self.driver_status)

        # Driver accepts
        self.client.logout()
        self.client.login(username='driver1', password='testpass123')
        self.client.post('/api/accept-driver-assignment/',
                         data=json.dumps({'assignment_id': a.id}),
                         content_type='application/json')
        rr.refresh_from_db()
        self.driver_status.refresh_from_db()
        self.assertEqual(rr.status, 'IN-PROGRESS')
        self.assertEqual(self.driver_status.status, 'IN_PROGRESS')

        # Driver completes
        self.client.post('/api/complete-driver-assignment/',
                         data=json.dumps({'assignment_id': a.id}),
                         content_type='application/json')
        rr.refresh_from_db()
        self.driver_status.refresh_from_db()
        self.assertEqual(rr.status, 'COMPLETED')
        self.assertEqual(self.driver_status.status, 'AVAILABLE')
        self.assertTrue(JobHistory.objects.filter(request=rr).exists())

    def test_E2E_dispatch_timeout_rotation(self):
        rr = self._make_request(status='ASSIGNED')
        Assignment.objects.create(
            request=rr, driver=self.driver_status,
            offer_sent_at=timezone.now() - timedelta(seconds=120),
            driver_response='TIMEOUT',
        )
        um_views._rotate_expired_dispatch_offers(rr)
        a = Assignment.objects.get(request=rr)
        self.assertEqual(a.driver_response, 'TIMEOUT')
        self.assertIsNotNone(a.driver_responded_at)

    def test_E2E_admin_manual_assignment(self):
        rr = self._make_request()
        self.client.login(username='admin1', password='testpass123')
        self.client.post(f'/dashboard/recovery-requests/{rr.id}/assign/',
                         {'driver_id': self.driver_status.id})
        rr.refresh_from_db()
        self.driver_status.refresh_from_db()
        self.assertEqual(rr.status, 'IN-PROGRESS')
        self.assertEqual(self.driver_status.status, 'IN_PROGRESS')
        a = Assignment.objects.get(request=rr)
        self.assertEqual(a.driver_response, 'ACCEPTED')

    def test_E2E_driver_decline_redispatch(self):
        # Two available drivers
        u2 = User.objects.create_user(username='d2', email='d2@t.com', password='p',
                                      role='DRIVER', status='APPROVED')
        ds2 = DriverStatus.objects.create(
            user=u2, status='AVAILABLE', license_number='L', vehicle_type='TOW_TRUCK',
            vehicle_registration='X', qualification=[], specialization=[self.service.id],
        )
        DriverLocation.objects.create(driver=u2, latitude=Decimal('53.5'), longitude=Decimal('-2.3'), is_current=True)

        rr = self._make_request()
        um_views._dispatch_to_next_optimal_drivers(rr)
        rr.refresh_from_db()
        a_first = Assignment.objects.filter(request=rr, driver=self.driver_status).first()

        self.client.login(username='driver1', password='testpass123')
        self.client.post('/api/accept-driver-assignment/',
                         data=json.dumps({'assignment_id': a_first.id, 'action': 'decline'}),
                         content_type='application/json')
        a_first.refresh_from_db()
        self.assertEqual(a_first.driver_response, 'DECLINED')
        # Other driver should still be assigned already (from initial dispatch) or after re-dispatch
        self.assertTrue(Assignment.objects.filter(request=rr, driver=ds2).exists())


class AdminUserCreationTests(TestCase):
    """Tests for admin_create_user and admin_create_driver views (docs/decisions/user-creation.md sec 9)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_creator',
            email='admin_creator@test.com',
            password='testpass123',
            role='ADMIN',
            status='APPROVED',
            active=True,
        )
        self.create_user_url = reverse('admin_create_user')
        self.create_driver_url = reverse('admin_create_driver')
        self.members_url = reverse('members')

    def _valid_member_data(self, **overrides):
        data = {
            'username': 'newmember',
            'email': 'newmember@test.com',
            'password': 'securepass1',
            'first_name': 'New',
            'last_name': 'Member',
            'phone': '+441234567',
        }
        data.update(overrides)
        return data

    def _valid_driver_data(self, **overrides):
        data = {
            'username': 'newdriver',
            'email': 'newdriver@test.com',
            'password': 'securepass1',
            'first_name': 'New',
            'last_name': 'Driver',
            'phone': '+441234567',
            'license_number': 'LIC-999',
            'vehicle_type': 'TOW_TRUCK',
            'vehicle_registration': 'ZZ99 ABC',
        }
        data.update(overrides)
        return data

    def test_create_member_happy_path(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.create_user_url, self._valid_member_data())

        self.assertRedirects(response, self.members_url, fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username='newmember').exists())
        user = User.objects.get(username='newmember')
        self.assertEqual(user.role, 'MEMBER')
        self.assertEqual(user.status, 'APPROVED')
        self.assertTrue(user.active)

        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.first_name, 'New')
        self.assertEqual(profile.last_name, 'Member')
        self.assertEqual(profile.phone, '+441234567')
        self.assertEqual(profile.membership_tier, 'STANDARD')

    def test_create_driver_happy_path(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.create_driver_url, self._valid_driver_data())

        self.assertRedirects(response, self.members_url, fetch_redirect_response=False)
        user = User.objects.get(username='newdriver')
        self.assertEqual(user.role, 'DRIVER')
        self.assertEqual(user.status, 'APPROVED')
        self.assertTrue(user.active)

        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.first_name, 'New')
        self.assertEqual(profile.membership_tier, 'STANDARD')

        ds = DriverStatus.objects.get(user=user)
        self.assertEqual(ds.status, 'OFFLINE')
        self.assertEqual(ds.license_number, 'LIC-999')
        self.assertEqual(ds.vehicle_type, 'TOW_TRUCK')
        self.assertEqual(ds.vehicle_registration, 'ZZ99 ABC')

    def test_duplicate_username_rejected(self):
        User.objects.create_user(
            username='takenname', email='taken@test.com',
            password='existingpass', role='MEMBER', status='APPROVED',
        )
        self.client.force_login(self.admin)
        count_before = User.objects.count()

        data = self._valid_member_data(username='takenname', email='other@test.com')
        response = self.client.post(self.create_user_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), count_before)
        self.assertIn('username', response.context['create_errors'])
        self.assertEqual(response.context['open_modal'], 'member')
        self.assertIn('already exists', response.context['create_errors']['username'].lower())
        # Preserved non-password field values are rendered
        self.assertIn('other@test.com', response.content.decode())

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            username='otheruser', email='taken@test.com',
            password='existingpass', role='MEMBER', status='APPROVED',
        )
        self.client.force_login(self.admin)
        count_before = User.objects.count()

        data = self._valid_member_data(username='brandnew', email='taken@test.com')
        response = self.client.post(self.create_user_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), count_before)
        self.assertFalse(User.objects.filter(username='brandnew').exists())
        self.assertIn('email', response.context['create_errors'])
        self.assertEqual(response.context['open_modal'], 'member')
        self.assertIn('already registered', response.context['create_errors']['email'].lower())
        self.assertIn('brandnew', response.content.decode())

    def test_missing_required_field(self):
        self.client.force_login(self.admin)
        count_before = User.objects.count()

        data = self._valid_member_data()
        data.pop('username')
        response = self.client.post(self.create_user_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), count_before)
        self.assertIn('username', response.context['create_errors'])
        self.assertEqual(response.context['open_modal'], 'member')
        self.assertIn('required', response.context['create_errors']['username'].lower())

    def test_driver_invalid_vehicle_type_rolls_back(self):
        self.client.force_login(self.admin)
        user_count_before = User.objects.count()
        profile_count_before = UserProfile.objects.count()
        ds_count_before = DriverStatus.objects.count()

        data = self._valid_driver_data(vehicle_type='SPACESHIP')
        response = self.client.post(self.create_driver_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), user_count_before)
        self.assertEqual(UserProfile.objects.count(), profile_count_before)
        self.assertEqual(DriverStatus.objects.count(), ds_count_before)
        self.assertFalse(User.objects.filter(username='newdriver').exists())
        self.assertIn('vehicle_type', response.context['create_errors'])
        self.assertEqual(response.context['open_modal'], 'driver')
        self.assertIn('vehicle type', response.context['create_errors']['vehicle_type'].lower())

    def test_non_admin_redirected(self):
        member = User.objects.create_user(
            username='plainmember', email='plainmember@test.com',
            password='memberpass1', role='MEMBER', status='APPROVED', active=True,
        )
        self.client.force_login(member)
        count_before = User.objects.count()

        response = self.client.post(self.create_driver_url, self._valid_driver_data())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), count_before)
        self.assertFalse(User.objects.filter(username='newdriver').exists())

    def test_get_request_is_noop(self):
        self.client.force_login(self.admin)
        count_before = User.objects.count()

        response_user = self.client.get(self.create_user_url)
        response_driver = self.client.get(self.create_driver_url)

        self.assertRedirects(response_user, self.members_url, fetch_redirect_response=False)
        self.assertRedirects(response_driver, self.members_url, fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), count_before)

    def test_driver_creation_stores_specialization(self):
        s1 = Service.objects.create(name='Tow', description='Tow svc', price='50', estimated_duration=30, active=True)
        s2 = Service.objects.create(name='Jumpstart', description='Jumpstart svc', price='30', estimated_duration=15, active=True)

        self.client.force_login(self.admin)
        data = self._valid_driver_data()
        data['specialization'] = [str(s1.id), str(s2.id)]
        response = self.client.post(self.create_driver_url, data)

        self.assertRedirects(response, self.members_url, fetch_redirect_response=False)
        ds = DriverStatus.objects.get(user__username='newdriver')
        self.assertEqual(sorted(ds.specialization), sorted([s1.id, s2.id]))

    def test_admin_supplied_password_can_login(self):
        self.client.force_login(self.admin)
        self.client.post(self.create_user_url, self._valid_member_data(
            username='logintestuser', email='logintest@test.com', password='mypassword9',
        ))
        self.assertTrue(User.objects.filter(username='logintestuser').exists())

        fresh = Client()
        logged_in = fresh.login(username='logintestuser', password='mypassword9')
        self.assertTrue(logged_in)
