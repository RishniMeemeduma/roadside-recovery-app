# Decision: Admin-Initiated User & Driver Creation

## 1. UI pattern
Two separate buttons ("Add Member" and "Add Driver") on `admin_users.html`, each opening its own `.admin-modal-*` modal. Rationale: driver forms need extra fields, and branching markup inside one modal via a role selector adds JS complexity we don't need.

## 2. Member creation fields
Required: `username`, `email`, `password`, `first_name`, `last_name`, `phone`. Optional: `address`, `membership_tier` (defaults STANDARD). Rationale: mirrors the self-serve `register_view` contract so admin-created members are indistinguishable from signups.

## 3. Driver creation fields
Superset of member fields plus required `license_number`, `vehicle_type` (select from `DriverStatus.VehicleType.choices`), `vehicle_registration`. `specialization` is left empty on create and edited later — keeps the modal short and avoids loading the Service list just to pick IDs. `qualification` defaults to `[]`.

## 4. Default values on creation
`status=APPROVED`, `active=True`, `deleted_at=None`, `UserProfile.membership_tier=STANDARD` (unless admin picks PREMIUM for members), `DriverStatus.status=OFFLINE`. Rationale: admin-created accounts must be immediately usable; drivers start OFFLINE until they log in and flip to AVAILABLE.

## 5. Validation rules
Before `create_user`: all required fields present; `username` not taken; `email` not taken and passes Django's `validate_email`; password length >= 8; phone is digits/`+`/spaces only and 7-15 chars; for drivers, `vehicle_type` is in `VehicleType.values` and `license_number`/`vehicle_registration` non-blank. Wrap user + profile + DriverStatus creation in `transaction.atomic()`.

## 6. Success/failure flow
Stick with POST-redirect + `django.contrib.messages`. Success redirects to `members` (named route `members`). Validation errors also redirect to `members` with `messages.error()` listing the problem. Rationale: matches existing admin-panel style; no form-state re-rendering infrastructure exists.

## 7. Password handling
Admin sets the password directly in the modal (plain input, min 8 chars). No email infra exists, so generating+emailing is out of scope. Admin can communicate the password to the user out-of-band.

## 8. Permission guard
Keep existing pattern: `if request.user.role != User.Role.ADMIN: return redirect('home')`. Also add `if request.method != 'POST': return redirect('members')` to prevent accidental GET. No tightening needed for academic scope.

## 9. Test coverage (tests-writer scope)
1. Admin can create a member with all required fields; user+profile rows exist, `status=APPROVED`, `active=True`.
2. Admin can create a driver; `DriverStatus` row exists with correct `vehicle_type`, `status=OFFLINE`.
3. Duplicate username rejected with error message, no user created.
4. Duplicate email rejected, no user created.
5. Missing required field (e.g. password) rejected.
6. Invalid `vehicle_type` on driver create rejected; no orphan User left (atomic).
7. Non-admin user hitting the endpoint is redirected to `home`, no user created.
8. GET request does not create a user.
9. Created member can log in with the admin-supplied password.

## 10. Bugs to fix + URL changes
- Both views redirect to `admin_dashboard` (name does not exist) → redirect to `members`.
- Neither view sets `status`, `active`; both must set `status=APPROVED`, `active=True`.
- `admin_create_driver` silently coerces missing phone to `"0000000000"` — remove, make phone required and validated.
- `urls.py` registers `create-user/` and `create-driver/` twice (lines 10-11 and 17-18) — remove duplicates.
- No new URLs needed; existing `admin_create_user` and `admin_create_driver` names are reused.
