"""Auth hardening — audit AUTH-01 (login brute-force throttle) + AUTH-03
(admin user-create must enforce the password validators) + min-length 12."""
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

STRONG = 'Str0ng-Passw0rd-2026'


class PasswordPolicyTest(TestCase):
    def setUp(self):
        cache.clear()
        self.dev = User.objects.create_user(
            email='dev@x.org', password=STRONG, full_name='Dev',
            organisation='CIPRB', role='developer',
        )

    def _dev_client(self):
        c = APIClient()
        c.force_authenticate(self.dev)
        return c

    def test_create_user_rejects_short_password(self):
        r = self._dev_client().post('/api/accounts/users/', {
            'email': 'weak@x.org', 'organisation': 'PHD', 'role': 'manager',
            'first_name': 'A', 'last_name': 'B', 'password': 'short',
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', r.data)
        self.assertFalse(User.objects.filter(email='weak@x.org').exists())

    def test_create_user_accepts_strong_password(self):
        r = self._dev_client().post('/api/accounts/users/', {
            'email': 'strong@x.org', 'organisation': 'PHD', 'role': 'manager',
            'first_name': 'A', 'last_name': 'B', 'password': STRONG,
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(User.objects.filter(email='strong@x.org').exists())


class LoginThrottleTest(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(
            email='u@x.org', password=STRONG, full_name='U',
            organisation='PHD', role='manager',
        )

    def test_login_throttled_after_10_per_min(self):
        c = APIClient()
        for i in range(10):
            r = c.post('/api/accounts/login/',
                       {'email': 'u@x.org', 'password': 'wrong'}, format='json')
            self.assertEqual(r.status_code, 400, f'attempt {i} -> {r.status_code}')
        r = c.post('/api/accounts/login/',
                   {'email': 'u@x.org', 'password': 'wrong'}, format='json')
        self.assertEqual(r.status_code, 429)

    def test_valid_login_within_limit_still_works(self):
        cache.clear()
        c = APIClient()
        r = c.post('/api/accounts/login/',
                   {'email': 'u@x.org', 'password': STRONG}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['user']['email'], 'u@x.org')
