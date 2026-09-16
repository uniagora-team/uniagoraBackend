from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.universities.models import University
from apps.vendors.models import (
    VendorDocument,
    VendorDocumentType,
    VendorProfile,
    VendorStatus,
    VendorType,
)

User = get_user_model()


class VendorProfileModelTests(TestCase):
    def setUp(self):
        self.university = University.objects.create(
            name="Uni of Ibadan", short_name="UI"
        )
        self.user = User.objects.create_user(
            email="student@example.com", password="pass12345", full_name="Student One"
        )

    def _student_profile(self, **overrides):
        data = dict(
            user=self.user,
            university=self.university,
            vendor_type=VendorType.STUDENT,
            store_name="Store A",
            phone_number="+2348012345678",
            matric_number="123456",
            department="CS",
            level="300",
        )
        data.update(overrides)
        return VendorProfile.objects.create(**data)

    def test_str_returns_store_name(self):
        vp = self._student_profile()
        self.assertEqual(str(vp), "Store A")

    def test_default_status_is_pending(self):
        vp = self._student_profile()
        self.assertEqual(vp.status, VendorStatus.PENDING)

    def test_is_verified_property(self):
        vp = self._student_profile()
        self.assertFalse(vp.is_verified)
        vp.status = VendorStatus.VERIFIED
        vp.save(update_fields=["status"])
        self.assertTrue(vp.is_verified)

    def test_matric_number_unique_per_university(self):
        self._student_profile()
        other_user = User.objects.create_user(
            email="student2@example.com", password="pass12345", full_name="Student Two"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._student_profile(user=other_user, matric_number="123456")

    def test_matric_number_unique_scoped_to_university(self):
        self._student_profile()
        other_university = University.objects.create(
            name="Uni of Lagos", short_name="UNILAG"
        )
        other_user = User.objects.create_user(
            email="student3@example.com",
            password="pass12345",
            full_name="Student Three",
        )
        # Same matric number, different university -> allowed.
        vp2 = self._student_profile(
            user=other_user, university=other_university, matric_number="123456"
        )
        self.assertIsNotNone(vp2.pk)

    def test_matric_number_reusable_after_soft_delete(self):
        """The uniqueness constraint is scoped to live rows, so a matric
        number freed by a soft-deleted application can be used again."""
        vp = self._student_profile()
        vp.delete()  # soft delete

        other_user = User.objects.create_user(
            email="student4@example.com",
            password="pass12345",
            full_name="Student Four",
        )
        # Must not raise IntegrityError.
        reprofile = self._student_profile(
            user=other_user,
            store_name="Store B",
            matric_number="123456",
        )
        self.assertFalse(reprofile.is_deleted)

    def test_business_vendors_do_not_collide_on_null_matric(self):
        u1 = User.objects.create_user(
            email="biz1@example.com", password="pass12345", full_name="Biz One"
        )
        u2 = User.objects.create_user(
            email="biz2@example.com", password="pass12345", full_name="Biz Two"
        )
        VendorProfile.objects.create(
            user=u1,
            university=self.university,
            vendor_type=VendorType.BUSINESS,
            store_name="B1",
            phone_number="+2348011111111",
            business_name="Biz1",
            business_address="Addr1",
        )
        vp2 = VendorProfile.objects.create(
            user=u2,
            university=self.university,
            vendor_type=VendorType.BUSINESS,
            store_name="B2",
            phone_number="+2348022222222",
            business_name="Biz2",
            business_address="Addr2",
        )
        self.assertIsNotNone(vp2.pk)

    def test_check_constraint_rejects_student_missing_required_fields(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            VendorProfile.objects.create(
                user=self.user,
                university=self.university,
                vendor_type=VendorType.STUDENT,
                store_name="X",
                phone_number="+2348011111111",
                # matric_number/department/level intentionally omitted
            )

    def test_check_constraint_rejects_business_missing_required_fields(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            VendorProfile.objects.create(
                user=self.user,
                university=self.university,
                vendor_type=VendorType.BUSINESS,
                store_name="X",
                phone_number="+2348011111111",
                # business_name/business_address intentionally omitted
            )

    def test_unfiltered_default_manager_includes_soft_deleted(self):
        vp = self._student_profile()
        vp.delete()  # soft delete
        self.assertTrue(VendorProfile.objects.filter(pk=vp.pk).exists())
        self.assertFalse(VendorProfile.objects.alive().filter(pk=vp.pk).exists())


class VendorDocumentModelTests(TestCase):
    def setUp(self):
        self.university = University.objects.create(
            name="Uni of Ibadan", short_name="UI"
        )
        self.user = User.objects.create_user(
            email="student@example.com", password="pass12345", full_name="Student One"
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.user,
            university=self.university,
            vendor_type=VendorType.STUDENT,
            store_name="Store A",
            phone_number="+2348012345678",
            matric_number="123456",
            department="CS",
            level="300",
        )

    def test_str_format(self):
        doc = VendorDocument.objects.create(
            vendor_profile=self.vendor_profile,
            document_type=VendorDocumentType.STUDENT_ID_CARD,
            file="https://example.com/id.pdf",
        )
        self.assertEqual(str(doc), "Store A — STUDENT_ID_CARD")

    def test_cascade_delete_with_vendor_profile_hard_delete(self):
        doc = VendorDocument.objects.create(
            vendor_profile=self.vendor_profile,
            document_type=VendorDocumentType.STUDENT_ID_CARD,
            file="https://example.com/id.pdf",
        )
        self.vendor_profile.delete(hard=True)
        self.assertFalse(VendorDocument.objects.filter(pk=doc.pk).exists())
