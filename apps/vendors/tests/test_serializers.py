from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.universities.models import University
from apps.vendors.models import VendorProfile, VendorType
from apps.vendors.serializers import (
    VendorApplicationSerializer,
    VendorProfileSerializer,
)

User = get_user_model()


class VendorApplicationSerializerTests(TestCase):
    def setUp(self):
        self.university = University.objects.create(
            name="Uni of Ibadan", short_name="UI"
        )

    def _doc(self):
        return SimpleUploadedFile(
            "id.pdf", b"filecontent", content_type="application/pdf"
        )

    def test_rejects_student_missing_required_fields(self):
        serializer = VendorApplicationSerializer(
            data={
                "university": self.university.pk,
                "vendor_type": VendorType.STUDENT,
                "store_name": "Store A",
                "phone_number": "+2348012345678",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("matric_number", serializer.errors)
        self.assertIn("department", serializer.errors)
        self.assertIn("level", serializer.errors)
        self.assertIn("document_type", serializer.errors)

    def test_rejects_business_missing_required_fields(self):
        serializer = VendorApplicationSerializer(
            data={
                "university": self.university.pk,
                "vendor_type": VendorType.BUSINESS,
                "store_name": "Store A",
                "phone_number": "+2348012345678",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("business_name", serializer.errors)
        self.assertIn("business_address", serializer.errors)

    def test_rejects_duplicate_matric_number_same_university(self):
        user = User.objects.create_user(
            email="s1@example.com", password="pass12345", full_name="S1"
        )
        VendorProfile.objects.create(
            user=user,
            university=self.university,
            vendor_type=VendorType.STUDENT,
            store_name="Store A",
            phone_number="+2348012345678",
            matric_number="123456",
            department="CS",
            level="300",
        )
        serializer = VendorApplicationSerializer(
            data={
                "university": self.university.pk,
                "vendor_type": VendorType.STUDENT,
                "store_name": "Store B",
                "phone_number": "+2348012345678",
                "matric_number": "123456",
                "department": "CS",
                "level": "200",
                "document_type": "STUDENT_ID_CARD",
                "document_file": self._doc(),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("matric_number", serializer.errors)

    def test_accepts_matric_number_freed_by_soft_deleted_application(self):
        """The friendly duplicate check only considers live applications."""
        user = User.objects.create_user(
            email="s1@example.com", password="pass12345", full_name="S1"
        )
        vp = VendorProfile.objects.create(
            user=user,
            university=self.university,
            vendor_type=VendorType.STUDENT,
            store_name="Store A",
            phone_number="+2348012345678",
            matric_number="123456",
            department="CS",
            level="300",
        )
        vp.delete()  # soft delete

        serializer = VendorApplicationSerializer(
            data={
                "university": self.university.pk,
                "vendor_type": VendorType.STUDENT,
                "store_name": "Store B",
                "phone_number": "+2348012345678",
                "matric_number": "123456",
                "department": "CS",
                "level": "200",
                "document_type": "STUDENT_ID_CARD",
                "document_file": self._doc(),
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_accepts_valid_student_payload(self):
        serializer = VendorApplicationSerializer(
            data={
                "university": self.university.pk,
                "vendor_type": VendorType.STUDENT,
                "store_name": "Store A",
                "phone_number": "+2348012345678",
                "matric_number": "123456",
                "department": "CS",
                "level": "300",
                "document_type": "STUDENT_ID_CARD",
                "document_file": self._doc(),
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_accepts_valid_business_payload(self):
        serializer = VendorApplicationSerializer(
            data={
                "university": self.university.pk,
                "vendor_type": VendorType.BUSINESS,
                "store_name": "Store B",
                "phone_number": "+2348012345678",
                "business_name": "Biz",
                "business_address": "Addr",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_business_document_type_for_student(self):
        serializer = VendorApplicationSerializer(
            data={
                "university": self.university.pk,
                "vendor_type": VendorType.STUDENT,
                "store_name": "Store A",
                "phone_number": "+2348012345678",
                "matric_number": "123456",
                "department": "CS",
                "level": "300",
                "document_type": "BUSINESS_DOCUMENT",
                "document_file": self._doc(),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("document_type", serializer.errors)


class VendorProfileSerializerTests(TestCase):
    def setUp(self):
        self.university = University.objects.create(
            name="Uni of Ibadan", short_name="UI"
        )
        self.user = User.objects.create_user(
            email="s1@example.com", password="pass12345", full_name="S1"
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

    def test_all_fields_are_read_only(self):
        data = VendorProfileSerializer(self.vendor_profile).data
        self.assertEqual(data["store_name"], "Store A")
        self.assertEqual(data["university"]["short_name"], "UI")
        self.assertIn("is_verified", data)
        self.assertIn("documents", data)
