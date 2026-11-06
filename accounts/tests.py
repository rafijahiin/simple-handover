from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Organisation, Role, User


def make_user(email, org, role, password='testpass123'):
    return User.objects.create_user(
        email=email,
        password=password,
        full_name='Test User',
        organisation=org,
        role=role,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class UserModelTest(TestCase):
    def test_create_user_sets_fields(self):
        user = make_user('a@phd.org', Organisation.PHD, Role.MANAGER)
        self.assertEqual(user.organisation, Organisation.PHD)
        self.assertEqual(user.role, Role.MANAGER)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)

    def test_email_is_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, 'email')

    def test_supervisor_can_see_all_orgs(self):
        user = make_user('a@ciprb.org', Organisation.CIPRB, Role.SUPERVISOR)
        self.assertTrue(user.can_see_all_orgs)

    def test_developer_can_see_all_orgs(self):
        user = make_user('dev@ciprb.org', Organisation.CIPRB, Role.DEVELOPER)
        self.assertTrue(user.can_see_all_orgs)

    def test_manager_cannot_see_all_orgs(self):
        user = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)
        self.assertFalse(user.can_see_all_orgs)

    def test_is_supervisor_property(self):
        user = make_user('a@unfpa.org', Organisation.UNFPA, Role.SUPERVISOR)
        self.assertTrue(user.is_supervisor)
        self.assertFalse(user.is_manager)
        self.assertFalse(user.is_developer)

    def test_is_manager_property(self):
        user = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)
        self.assertTrue(user.is_manager)
        self.assertFalse(user.is_supervisor)
        self.assertFalse(user.is_developer)

    def test_is_org_lead_property(self):
        user = make_user('s@ciprb.org', Organisation.CIPRB, Role.ORG_LEAD)
        self.assertTrue(user.is_org_lead)
        self.assertFalse(user.is_supervisor)
        self.assertFalse(user.is_manager)

    def test_can_configure_targets_method(self):
        sup = make_user('sup@unfpa.org', Organisation.UNFPA, Role.SUPERVISOR)
        self.assertTrue(sup.can_configure_targets('PHD'))
        self.assertTrue(sup.can_configure_targets('Bandhu'))
        self.assertTrue(sup.can_configure_targets('CIPRB'))

        # Per Animesh's 2026-06-01 directive, org leads do NOT configure targets
        # (UNFPA sets them; partners track against them) — can_configure_targets
        # returns True only for DEVELOPER/SUPERVISOR. A CIPRB org lead is denied
        # for every partner, including its own.
        lead_ciprb = make_user('lead@ciprb.org', Organisation.CIPRB, Role.ORG_LEAD)
        self.assertFalse(lead_ciprb.can_configure_targets('CIPRB'))
        self.assertFalse(lead_ciprb.can_configure_targets('PHD'))
        self.assertFalse(lead_ciprb.can_configure_targets('Bandhu'))

        mgr = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)
        self.assertFalse(mgr.can_configure_targets('PHD'))

    def test_can_access_mpdsr(self):
        # Dev + Supervisor + CIPRB Org Lead + CIPRB Manager → True
        self.assertTrue(make_user('d@x', Organisation.CIPRB, Role.DEVELOPER).can_access_mpdsr)
        self.assertTrue(make_user('s@x', Organisation.UNFPA, Role.SUPERVISOR).can_access_mpdsr)
        self.assertTrue(make_user('o@ciprb', Organisation.CIPRB, Role.ORG_LEAD).can_access_mpdsr)
        # CIPRB Manager (Tanjina = the CIPRB approver) → True (2026-06-26 grant).
        self.assertTrue(make_user('mc@ciprb', Organisation.CIPRB, Role.MANAGER).can_access_mpdsr)
        # CRITICAL guard rail — non-CIPRB managers must NEVER reach CIPRB PII
        # (audit FIX C1). The org-bound clause keeps PHD/Bandhu managers out.
        self.assertFalse(make_user('mp@phd', Organisation.PHD, Role.MANAGER).can_access_mpdsr)
        self.assertFalse(make_user('mb@bandhu', Organisation.BANDHU, Role.MANAGER).can_access_mpdsr)
        self.assertFalse(make_user('fp@phd', Organisation.PHD, Role.FOCAL).can_access_mpdsr)
        self.assertFalse(make_user('fs@phd', Organisation.PHD, Role.FIELD_STAFF).can_access_mpdsr)
        self.assertFalse(make_user('fc@ciprb', Organisation.CIPRB, Role.FIELD_STAFF).can_access_mpdsr)
        self.assertFalse(make_user('cb@ciprb', Organisation.CIPRB, Role.CIPRB_BASELINE).can_access_mpdsr)

    def test_can_access_fistula_cases(self):
        # Same CIPRB-approver rule as MPDSR — both gate decrypted survivor/death PII.
        self.assertTrue(make_user('d2@x', Organisation.CIPRB, Role.DEVELOPER).can_access_fistula_cases)
        self.assertTrue(make_user('s2@x', Organisation.UNFPA, Role.SUPERVISOR).can_access_fistula_cases)
        self.assertTrue(make_user('o2@ciprb', Organisation.CIPRB, Role.ORG_LEAD).can_access_fistula_cases)
        self.assertTrue(make_user('mc2@ciprb', Organisation.CIPRB, Role.MANAGER).can_access_fistula_cases)
        # CRITICAL guard rail — non-CIPRB managers denied (audit FIX C1).
        self.assertFalse(make_user('mp2@phd', Organisation.PHD, Role.MANAGER).can_access_fistula_cases)
        self.assertFalse(make_user('mb2@bandhu', Organisation.BANDHU, Role.MANAGER).can_access_fistula_cases)
        self.assertFalse(make_user('fs2@phd', Organisation.PHD, Role.FIELD_STAFF).can_access_fistula_cases)
        self.assertFalse(make_user('cb2@ciprb', Organisation.CIPRB, Role.CIPRB_BASELINE).can_access_fistula_cases)

    def test_can_enter_field_records_excludes_manager(self):
        # The handoff says managers approve, they do NOT enter HTC/HIV/STI/GBV/MH.
        self.assertFalse(make_user('m1@x', Organisation.PHD, Role.MANAGER).can_enter_field_records)
        self.assertTrue(make_user('fs@x', Organisation.PHD, Role.FIELD_STAFF).can_enter_field_records)

    def test_can_enter_outreach_records_excludes_field_staff(self):
        # Outreach is manager-mandatory; field staff record clinical encounters.
        self.assertTrue(make_user('m2@x', Organisation.PHD, Role.MANAGER).can_enter_outreach_records)
        self.assertFalse(make_user('fs2@x', Organisation.PHD, Role.FIELD_STAFF).can_enter_outreach_records)

    def test_create_superuser_sets_flags(self):
        user = User.objects.create_superuser('admin@ciprb.org', 'pass123')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_user_str_contains_org(self):
        user = make_user('a@phd.org', Organisation.PHD, Role.MANAGER)
        self.assertIn('PHD', str(user))

    def test_email_is_normalised(self):
        user = make_user('Test@PHD.ORG', Organisation.PHD, Role.MANAGER)
        self.assertEqual(user.email, 'Test@phd.org')

    def test_no_email_raises(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(
                email='',
                password='pass123',
                full_name='No Email',
                organisation=Organisation.PHD,
            )


# ---------------------------------------------------------------------------
# Login view
# ---------------------------------------------------------------------------

class LoginViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('login')
        self.manager = make_user('manager@phd.org', Organisation.PHD, Role.MANAGER)

    def test_login_success_manager(self):
        r = self.client.post(self.url, {'email': 'manager@phd.org', 'password': 'testpass123'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['requires_2fa'])
        self.assertEqual(r.data['user']['email'], 'manager@phd.org')
        self.assertEqual(r.data['user']['organisation'], 'PHD')

    def test_login_wrong_password(self):
        r = self.client.post(self.url, {'email': 'manager@phd.org', 'password': 'wrongpass'})
        self.assertEqual(r.status_code, 400)

    def test_login_missing_fields(self):
        r = self.client.post(self.url, {'email': 'manager@phd.org'})
        self.assertEqual(r.status_code, 400)

    def test_login_supervisor_no_2fa(self):
        """TOTP was removed — supervisors log in like everyone else."""
        make_user('admin@ciprb.org', Organisation.CIPRB, Role.SUPERVISOR)
        r = self.client.post(self.url, {'email': 'admin@ciprb.org', 'password': 'testpass123'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['requires_2fa'])
        self.assertEqual(r.data['user']['role'], 'supervisor')

    def test_login_inactive_user(self):
        self.manager.is_active = False
        self.manager.save()
        r = self.client.post(self.url, {'email': 'manager@phd.org', 'password': 'testpass123'})
        self.assertEqual(r.status_code, 400)


# ---------------------------------------------------------------------------
# Me view
# ---------------------------------------------------------------------------

class MeViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)

    def test_me_authenticated_returns_user_data(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get(reverse('me'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['organisation'], 'PHD')
        self.assertEqual(r.data['role'], 'manager')

    def test_me_unauthenticated_returns_403(self):
        r = self.client.get(reverse('me'))
        self.assertEqual(r.status_code, 403)

    def test_me_does_not_expose_password(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get(reverse('me'))
        self.assertNotIn('password', r.data)


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

class PasswordChangeViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)
        self.client.force_authenticate(user=self.user)
        self.url = reverse('password-change')

    def test_password_change_success(self):
        r = self.client.post(self.url, {
            'current_password': 'testpass123',
            'new_password': 'NewSecurePass456!',
        })
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecurePass456!'))

    def test_wrong_current_password_rejected(self):
        r = self.client.post(self.url, {
            'current_password': 'wrongpass',
            'new_password': 'NewSecurePass456!',
        })
        self.assertEqual(r.status_code, 400)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        r = self.client.post(self.url, {
            'current_password': 'testpass123',
            'new_password': 'NewSecurePass456!',
        })
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# Logout view
# ---------------------------------------------------------------------------

class LogoutViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)

    def test_logout_success(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.post(reverse('logout'))
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Org isolation — middleware attaches correct attributes
# ---------------------------------------------------------------------------

class OrgMiddlewareTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phd_manager = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)
        self.bondhu_manager = make_user('m@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def test_phd_manager_org_in_response(self):
        self.client.force_authenticate(user=self.phd_manager)
        r = self.client.get(reverse('me'))
        self.assertEqual(r.data['organisation'], 'PHD')

    def test_bondhu_manager_org_in_response(self):
        self.client.force_authenticate(user=self.bondhu_manager)
        r = self.client.get(reverse('me'))
        self.assertEqual(r.data['organisation'], 'Bandhu')


# ---------------------------------------------------------------------------
# User management (developer-only — audit FIX 1.4)
# ---------------------------------------------------------------------------

class UserViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.developer = make_user('dev@ciprb.org', Organisation.CIPRB, Role.DEVELOPER)
        self.supervisor = make_user('sup@unfpa.org', Organisation.UNFPA, Role.SUPERVISOR)
        self.org_lead = make_user('lead@ciprb.org', Organisation.CIPRB, Role.ORG_LEAD)
        self.manager = make_user('m@phd.org', Organisation.PHD, Role.MANAGER)

    def test_manager_cannot_list_users(self):
        self.client.force_authenticate(user=self.manager)
        r = self.client.get('/api/accounts/users/')
        # 403 — IsDeveloperOnly rejects non-developer (audit FIX 1.4)
        self.assertEqual(r.status_code, 403)

    def test_supervisor_cannot_list_users(self):
        """Audit FIX 1.4 — supervisor no longer has user-mgmt access."""
        self.client.force_authenticate(user=self.supervisor)
        r = self.client.get('/api/accounts/users/')
        self.assertEqual(r.status_code, 403)

    def test_org_lead_cannot_list_users(self):
        """Audit FIX 1.4 — org_lead never had user-mgmt access, double-check."""
        self.client.force_authenticate(user=self.org_lead)
        r = self.client.get('/api/accounts/users/')
        self.assertEqual(r.status_code, 403)

    def test_developer_can_list_users(self):
        """Audit FIX 1.4 — developer is the only role that manages users."""
        self.client.force_authenticate(user=self.developer)
        r = self.client.get('/api/accounts/users/')
        self.assertEqual(r.status_code, 200)
