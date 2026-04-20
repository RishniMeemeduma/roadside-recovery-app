"""Tests for Service model."""
from django.test import TestCase

from services.models import Service


class TestServiceModel(TestCase):
    def test_SV01_create(self):
        s = Service.objects.create(
            name='Battery', description='Jump start',
            price='29.99', estimated_duration='20 min',
        )
        self.assertTrue(s.active)
        self.assertEqual(s.name, 'Battery')

    def test_SV02_soft_delete(self):
        s = Service.objects.create(name='x', description='d', price='1', estimated_duration='1')
        s.active = False
        s.save()
        self.assertFalse(Service.objects.filter(active=True, id=s.id).exists())
        self.assertTrue(Service.objects.filter(id=s.id).exists())

    def test_SV03_price_as_string(self):
        s = Service.objects.create(name='x', description='d', price='29.99', estimated_duration='1')
        self.assertEqual(s.price, '29.99')
        self.assertIsInstance(s.price, str)
