# QuickAssist Northwest — Testing Plan

## 1. Testing Strategy

### Approach
- **Framework:** Django's built-in `TestCase` and `Client` (no external testing libraries required)
- **Database:** Each test uses a temporary SQLite database (auto-created by Django test runner)
- **Scope:** Unit tests for models/helpers, integration tests for views/API endpoints, manual tests for UI/UX flows

### Running Tests
```bash
# All tests
python manage.py test

# Specific app
python manage.py test usermanagement
python manage.py test recovery
python manage.py test services

# Specific test class
python manage.py test usermanagement.tests.TestDriverDispatch

# With verbosity
python manage.py test -v 2
```

### Test File Structure
```
usermanagement/tests.py    — Auth, user management, driver workflow, dispatch, API endpoints
recovery/tests.py          — Models (RecoveryRequest, Assignment, JobHistory)
services/tests.py          — Service model CRUD
core/tests.py              — Home page view
```

---

## 2. Unit Tests — Models

### 2.1 User Model (`usermanagement/tests.py`)

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| UM-01 | Create member user | role=MEMBER, email, username | User created with status=PENDING, active=True |
| UM-02 | Create driver user | role=DRIVER, email, username | User created with status=PENDING |
| UM-03 | Create admin user | role=ADMIN | User created successfully |
| UM-04 | Email uniqueness | Two users with same email | IntegrityError raised |
| UM-05 | UUID primary key | Create user | user.uuid is a valid UUID4 |
| UM-06 | Soft delete | Set active=False, deleted_at=now | User still exists in DB, active=False |
| UM-07 | Default status | Create user without status | status defaults to PENDING |

### 2.2 UserProfile Model

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| UP-01 | Create profile | user, first_name, last_name, phone, address | Profile linked to user via OneToOne |
| UP-02 | Default membership tier | Create without tier | membership_tier defaults to STANDARD |
| UP-03 | Profile access via user | user.profile | Returns the linked UserProfile |

### 2.3 DriverStatus Model

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| DS-01 | Create driver status | user, license, vehicle_type, registration | DriverStatus created, status=AVAILABLE |
| DS-02 | Valid vehicle types | MOBILE_UNIT, TOW_TRUCK, FLATBED | All accepted |
| DS-03 | Invalid vehicle type | vehicle_type='HELICOPTER' | Validation error |
| DS-04 | Specialization as JSON | specialization=[1, 2, 3] | Stored and retrieved as list |
| DS-05 | Qualification as JSON | qualification=['MOT', 'HGV'] | Stored and retrieved as list |

### 2.4 DriverLocation Model

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| DL-01 | Create location | driver, lat, lon | Location created with is_current=True |
| DL-02 | Multiple locations | Create two for same driver | Both exist, can filter by is_current |
| DL-03 | Coordinate precision | lat=53.483959, lon=-2.244644 | Stored with 6 decimal places |

### 2.5 RecoveryRequest Model (`recovery/tests.py`)

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| RR-01 | Create request | member, service, lat/lon, address, issue | Request created, status=PENDING |
| RR-02 | Default priority | Create without priority | priority=NORMAL |
| RR-03 | Valid statuses | PENDING, ASSIGNED, IN-PROGRESS, COMPLETED, CANCELLED | All accepted |
| RR-04 | Place values | MOTORWAY, ROAD, NEAR HOUSE | All accepted |
| RR-05 | FK to member | request.member | Returns the linked User |
| RR-06 | FK to service | request.service | Returns the linked Service |

### 2.6 Assignment Model

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| AS-01 | Create assignment | request, driver, offer_sent_at | Assignment created |
| AS-02 | Driver response values | ACCEPTED, DECLINED, TIMEOUT | All accepted |
| AS-03 | Multiple assignments per request | Create 3 assignments for 1 request | All linked via request FK |
| AS-04 | Accepted timestamp | Set driver_response=ACCEPTED | accepted_at can be set |
| AS-05 | Cancellation reason | Set cancellation_reason text | Stored correctly |

### 2.7 JobHistory Model

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| JH-01 | Create job history | request, driver, assignment, times | JobHistory created |
| JH-02 | OneToOne with request | Create two for same request | IntegrityError on second |
| JH-03 | Completion time | start=12:00, end=12:45 | completion_time_minutes=45 |
| JH-04 | Optional rating | member_rating=None | Allowed (nullable) |

### 2.8 Service Model (`services/tests.py`)

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| SV-01 | Create service | name, description, price, duration | Service created, active=True |
| SV-02 | Soft delete | Set active=False | Service still in DB, not shown in active queries |
| SV-03 | Price as string | price='29.99' | Stored as CharField |

---

## 3. Unit Tests — Helper Functions

### 3.1 Haversine Distance (`usermanagement/tests.py`)

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| HV-01 | Known distance | Manchester (53.48, -2.24) to Liverpool (53.41, -2.98) | ~50 km (within 5% tolerance) |
| HV-02 | Same point | (0, 0) to (0, 0) | 0 km |
| HV-03 | Antipodal points | (0, 0) to (0, 180) | ~20015 km |

### 3.2 Service Matching

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| SM-01 | Driver supports service | specialization=[1,2], service.id=1 | True |
| SM-02 | Driver doesn't support service | specialization=[3], service.id=1 | False |
| SM-03 | Empty specialization | specialization=[] | False |

### 3.3 Driver Ranking

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| DR-01 | Rank by distance | 3 drivers at different distances | Closest driver first |
| DR-02 | Exclude unavailable | 1 AVAILABLE, 1 OFFLINE | Only AVAILABLE in results |
| DR-03 | Exclude without location | 1 with location, 1 without | Only driver with location returned |
| DR-04 | Exclude already offered | driver in excluded_ids | Not in results |

### 3.4 Dispatch Logic

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| DP-01 | Dispatch batch size | 5 available drivers | Only 3 assignments created (DISPATCH_BATCH_SIZE) |
| DP-02 | No available drivers | 0 available drivers | Request stays PENDING, returns 0 |
| DP-03 | Fewer than batch | 2 available drivers | 2 assignments created |

### 3.5 Offer Rotation

| ID | Test Case | Input | Expected Result |
|----|-----------|-------|-----------------|
| OR-01 | Unexpired offer | offer_sent 30s ago | No rotation, returns 0 |
| OR-02 | Expired offer | offer_sent 61s ago | Offer set to TIMEOUT, next batch dispatched |
| OR-03 | Already accepted | Assignment with ACCEPTED response | No rotation (returns 0) |
| OR-04 | No pending offers | All offers responded | Triggers new dispatch |

---

## 4. Integration Tests — Views & API Endpoints

### 4.1 Authentication

| ID | Test Case | Method | URL | Expected |
|----|-----------|--------|-----|----------|
| AU-01 | Register member | POST | /signup/ | User created, redirect to login |
| AU-02 | Register driver | POST | /signup/ | User + DriverStatus created |
| AU-03 | Register duplicate email | POST | /signup/ | Error message, no user created |
| AU-04 | Login valid credentials | POST | /login/ | Session created, redirect to dashboard |
| AU-05 | Login invalid credentials | POST | /login/ | Error message, no session |
| AU-06 | Login pending user | POST | /login/ | Error: account not approved |
| AU-07 | Logout | GET | /logout/ | Session destroyed, redirect to home |
| AU-08 | Dashboard redirect unauthenticated | GET | /dashboard/ | Redirect to login |

### 4.2 Member Dashboard & Requests

| ID | Test Case | Method | URL | Expected |
|----|-----------|--------|-----|----------|
| MR-01 | View member dashboard | GET | /dashboard/ | 200, shows services |
| MR-02 | Submit valid request | POST | /submit-request/ | RecoveryRequest created, status=ASSIGNED or PENDING |
| MR-03 | Submit without service | POST | /submit-request/ | Error message |
| MR-04 | Submit without address | POST | /submit-request/ | Error message |
| MR-05 | Cancel pending request | POST | /cancel-request/1/ | Request status=CANCELLED |
| MR-06 | Cancel completed request | POST | /cancel-request/1/ | Error: cannot cancel |
| MR-07 | Cancel another user's request | POST | /cancel-request/1/ | 403 or redirect |
| MR-08 | Member requests status API | GET | /api/member-requests-status/ | JSON with today's request statuses |
| MR-09 | Member track driver location | GET | /api/member-request-driver-location/1/ | JSON with driver lat/lon |
| MR-10 | DVLA vehicle lookup | POST | /lookup-vehicle/ | JSON with vehicle details (requires API key) |

### 4.3 Driver Dashboard & Assignment Workflow

| ID | Test Case | Method | URL | Expected |
|----|-----------|--------|-----|----------|
| DW-01 | View driver dashboard | GET | /dashboard/ | 200, shows assignment or waiting state |
| DW-02 | Go online | POST | /api/update-driver-status/ | driver.status=AVAILABLE |
| DW-03 | Go offline | POST | /api/update-driver-status/ | driver.status=OFFLINE |
| DW-04 | Go offline with active job | POST | /api/update-driver-status/ | 409 error |
| DW-05 | Accept assignment | POST | /api/accept-driver-assignment/ | Assignment ACCEPTED, request IN-PROGRESS |
| DW-06 | Accept expired assignment | POST | /api/accept-driver-assignment/ | 409, offer expired |
| DW-07 | Decline assignment | POST | /api/accept-driver-assignment/ | Assignment DECLINED, next drivers dispatched |
| DW-08 | Complete assignment | POST | /api/complete-driver-assignment/ | JobHistory created, driver AVAILABLE |
| DW-09 | Cancel assignment | POST | /api/cancel-driver-assignment/ | Request CANCELLED, driver AVAILABLE |
| DW-10 | Request assistance | POST | /api/request-driver-assistance/ | assistance_requested_at set |
| DW-11 | Update location | POST | /api/update-location/ | DriverLocation created, is_current=True |
| DW-12 | Assignment snapshot | GET | /api/driver-assignment-snapshot/ | JSON with feed_version, has_assignment |
| DW-13 | Dispatch card partial | GET | /api/driver-dispatch-card/ | HTML fragment with card content |
| DW-14 | Non-driver access snapshot | GET | /api/driver-assignment-snapshot/ | 403 |

### 4.4 Admin Operations

| ID | Test Case | Method | URL | Expected |
|----|-----------|--------|-----|----------|
| AD-01 | View admin dashboard | GET | /dashboard/ | 200, shows stats and counts |
| AD-02 | View recovery requests | GET | /dashboard/recovery-requests/ | 200, table with all requests |
| AD-03 | Assign request to driver | POST | /dashboard/recovery-requests/1/assign/ | Request IN-PROGRESS, driver IN_PROGRESS |
| AD-04 | Assign to unavailable driver | POST | /dashboard/recovery-requests/1/assign/ | 404 (driver not in available queryset) |
| AD-05 | Assign non-pending request | POST | /dashboard/recovery-requests/1/assign/ | Error: only pending can be assigned |
| AD-06 | Decline request | POST | /dashboard/recovery-requests/1/decline/ | Request CANCELLED |
| AD-07 | Create user | POST | /dashboard/create-user/ | User created |
| AD-08 | Create driver | POST | /dashboard/create-driver/ | User + DriverStatus created |
| AD-09 | Delete user | POST | /dashboard/delete-user/<uuid>/ | User soft-deleted |
| AD-10 | Approve user registration | POST | /dashboard/handle-request/<uuid>/ | User status=APPROVED |
| AD-11 | Reject user registration | POST | /dashboard/handle-request/<uuid>/ | User status=REJECTED |
| AD-12 | View services | GET | /dashboard/services/ | 200, service list |
| AD-13 | Create service | POST | /dashboard/services/ | Service created |
| AD-14 | Delete service | POST | /dashboard/delete-service/1/ | Service active=False |
| AD-15 | View analytics | GET | /dashboard/analytics/ | 200, charts + stats render |
| AD-16 | Driver locations API | GET | /api/driver-locations/ | JSON with available driver positions |
| AD-17 | Requests status API | GET | /api/admin-requests-status/ | JSON with active request statuses |
| AD-18 | Non-admin access admin page | GET | /dashboard/recovery-requests/ | Redirect to home |

### 4.5 Role-Based Access Control

| ID | Test Case | Role | URL | Expected |
|----|-----------|------|-----|----------|
| AC-01 | Member accesses admin page | MEMBER | /dashboard/recovery-requests/ | Redirect to home |
| AC-02 | Driver accesses admin page | DRIVER | /dashboard/services/ | Redirect to home |
| AC-03 | Member accesses driver API | MEMBER | /api/update-driver-status/ | 403 |
| AC-04 | Driver accesses member API | DRIVER | /api/member-requests-status/ | 403 |
| AC-05 | Admin accesses driver snapshot | ADMIN | /api/driver-assignment-snapshot/ | 403 |
| AC-06 | Unauthenticated user | None | /dashboard/ | Redirect to login |

---

## 5. End-to-End Flow Tests

### 5.1 Full Member Request Lifecycle

```
1. Create member user (APPROVED)
2. Create driver user (APPROVED) with DriverStatus (AVAILABLE) and DriverLocation
3. Create a Service
4. Login as member
5. POST /submit-request/ with valid data
   → Assert: RecoveryRequest created, status=ASSIGNED
   → Assert: Assignment created for the driver
6. Login as driver
7. POST /api/accept-driver-assignment/ with assignment_id
   → Assert: Request status=IN-PROGRESS, driver status=IN_PROGRESS
8. POST /api/complete-driver-assignment/ with assignment_id
   → Assert: Request status=COMPLETED, JobHistory created, driver=AVAILABLE
```

### 5.2 Dispatch Timeout & Rotation

```
1. Create request, dispatch to driver (Assignment created)
2. Fast-forward time by 61 seconds (mock timezone.now)
3. Trigger _rotate_expired_dispatch_offers()
   → Assert: Assignment.driver_response=TIMEOUT
   → Assert: New dispatch attempted to next drivers
```

### 5.3 Admin Manual Assignment

```
1. Create PENDING request (no auto-dispatch or all drivers timed out)
2. Login as admin
3. POST assign request to specific driver
   → Assert: Request status=IN-PROGRESS (not ASSIGNED)
   → Assert: Assignment created with ACCEPTED response
   → Assert: Driver status=IN_PROGRESS
4. Verify driver dashboard snapshot shows the assignment
```

### 5.4 Driver Decline & Re-dispatch

```
1. Create request, auto-dispatch to driver
2. Driver calls accept endpoint with action='decline'
   → Assert: Assignment.driver_response=DECLINED
   → Assert: _dispatch_to_next_optimal_drivers called
   → Assert: If other drivers available, new assignments created
   → Assert: If no drivers available, request stays PENDING
```

---

## 6. Manual Testing Checklist

### 6.1 UI/UX Tests (browser-based)

| ID | Test | Steps | Expected |
|----|------|-------|----------|
| UI-01 | Registration form toggle | Select "Driver" in role dropdown | Driver fields (license, vehicle type) appear |
| UI-02 | Member dashboard services | Login as member | Service cards displayed from DB |
| UI-03 | Request submission form | Fill form and submit | Success message, request appears in status |
| UI-04 | Driver dispatch card appears | Admin assigns job to driver | Card appears on driver dashboard within 5s, alert sound plays |
| UI-05 | Driver status button | Click "Go Online" / "Go Offline" | Button toggles, status updates |
| UI-06 | Offer countdown timer | Driver receives ASSIGNED offer | Timer counts down from 60s |
| UI-07 | Job location map | Driver accepts job | Leaflet map shows job location |
| UI-08 | Navigation button | Click "Start Navigation" | Opens Google Maps with directions |
| UI-09 | Location sharing | Click "Start Sharing" | Indicator turns green, "Active" text |
| UI-10 | Admin live map | Open admin recovery requests | Driver markers on Leaflet map, update every 5s |
| UI-11 | Admin request details | Click "View" on a request | Expandable panel shows full details + assignment history |
| UI-12 | Admin status live update | Submit request from member | Admin table updates status within 10s |
| UI-13 | Analytics charts | Open analytics page | Line chart + bar chart render with real data |
| UI-14 | Mobile responsiveness | View on 375px width | Cards stack, tables scroll, buttons accessible |

### 6.2 Edge Cases

| ID | Test | Expected |
|----|------|----------|
| EC-01 | Submit request with no available drivers | Request stays PENDING, no assignments created |
| EC-02 | Two drivers accept same request simultaneously | First accepted, second gets 409 error |
| EC-03 | Driver goes offline during active job | 409 error, must complete/cancel first |
| EC-04 | Admin assigns to driver who just went offline | 404 (driver not in available queryset) |
| EC-05 | Cancel request that's already completed | Error message, no status change |
| EC-06 | DVLA lookup with invalid registration | API returns error, shown to user |
| EC-07 | Refresh driver dashboard rapidly | No duplicate dispatches or state corruption |

---

## 7. Test Data Setup

### Shared Test Fixtures

```python
# Base test class with common setup
class BaseTestCase(TestCase):
    def setUp(self):
        # Admin user
        self.admin = User.objects.create_user(
            username='admin1', email='admin@test.com',
            password='testpass123', role='ADMIN', status='APPROVED'
        )
        # Member user
        self.member = User.objects.create_user(
            username='member1', email='member@test.com',
            password='testpass123', role='MEMBER', status='APPROVED'
        )
        # Driver user + status + location
        self.driver_user = User.objects.create_user(
            username='driver1', email='driver@test.com',
            password='testpass123', role='DRIVER', status='APPROVED'
        )
        self.driver_status = DriverStatus.objects.create(
            user=self.driver_user,
            status='AVAILABLE',
            license_number='DRV123',
            vehicle_type='TOW_TRUCK',
            vehicle_registration='AB12 CDE',
            specialization=[1],
        )
        self.driver_location = DriverLocation.objects.create(
            driver=self.driver_user,
            latitude=53.4808,
            longitude=-2.2426,
            is_current=True,
        )
        # Service
        self.service = Service.objects.create(
            name='Towing', description='Vehicle towing',
            price='49.99', estimated_duration='45 min',
        )
```

---

## 8. Test Coverage Targets

| Area | Target | Priority |
|------|--------|----------|
| Models (all apps) | 90%+ | High |
| Helper functions (haversine, dispatch, rotation) | 100% | High |
| View endpoints (auth, member, driver, admin) | 80%+ | High |
| Role-based access control | 100% | High |
| API JSON endpoints | 90%+ | Medium |
| Template rendering (no errors) | All pages | Medium |
| Edge cases | All listed | Low |

---

## 9. Execution Plan

| Phase | Scope | Est. Tests |
|-------|-------|-----------|
| Phase 1 | Model unit tests (all apps) | ~25 tests |
| Phase 2 | Helper function tests (haversine, dispatch, rotation) | ~15 tests |
| Phase 3 | Auth & access control integration tests | ~15 tests |
| Phase 4 | Member workflow integration tests | ~10 tests |
| Phase 5 | Driver workflow integration tests | ~15 tests |
| Phase 6 | Admin workflow integration tests | ~18 tests |
| Phase 7 | End-to-end flow tests | ~4 tests |
| Phase 8 | Manual UI/UX testing | ~14 checks |
| **Total** | | **~116 tests** |
