"""Tests for core home view."""
from django.test import TestCase


class TestHomeView(TestCase):
    def test_home_renders(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
