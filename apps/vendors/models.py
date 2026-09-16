from django.conf import settings
from django.db import models
from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.fields import CloudinaryDocumentField, CloudinaryImageField
from apps.common.models import BaseModel
from apps.common.validators import validate_phone_number
from apps.universities.models import University


class VendorType(models.TextChoices):
    STUDENT = "STUDENT", "Student Vendor"
    BUSINESS = "BUSINESS", "Business Vendor"


class VendorStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"


class VendorDocumentType(models.TextChoices):
    ADMISSION_LETTER = "ADMISSION_LETTER", "Admission Letter"
    STUDENT_ID_CARD = "STUDENT_ID_CARD", "Student ID Card"
    COURSE_REGISTRATION_SLIP = "COURSE_REGISTRATION_SLIP", "Course Registration Slip"
    SCHOOL_FEE_RECEIPT = "SCHOOL_FEE_RECEIPT", "School Fee Receipt"
    BUSINESS_DOCUMENT = "BUSINESS_DOCUMENT", "Business Document"  # reserved, unused MVP


class VendorDocumentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class VendorProfile(BaseModel):
    """DDS §4.3. Customer's upgrade to Vendor status."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vendor_profile",
    )
    university = models.ForeignKey(
        University,
        on_delete=models.PROTECT,
        related_name="vendor_profiles",
    )
    vendor_type = models.CharField(max_length=20, choices=VendorType.choices)
    store_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, validators=[validate_phone_number])

    # Student-vendor-only fields
    matric_number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    department = models.CharField(max_length=100, null=True, blank=True)  # noqa: DJ001
    level = models.CharField(max_length=10, null=True, blank=True)  # noqa: DJ001

    # Business-vendor-only fields
    business_name = models.CharField(max_length=150, null=True, blank=True)  # noqa: DJ001
    business_address = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    business_logo = CloudinaryImageField(folder="vendor_logos", null=True, blank=True)  # noqa: DJ001

    status = models.CharField(
        max_length=20,
        choices=VendorStatus.choices,
        default=VendorStatus.PENDING,
        db_index=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_reviews",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["university", "matric_number"],
                condition=Q(matric_number__isnull=False) & Q(is_deleted=False),
                name="unique_matric_number_per_university",
            ),
            models.CheckConstraint(
                check=(
                    Q(
                        vendor_type=VendorType.STUDENT,
                        matric_number__isnull=False,
                        department__isnull=False,
                        level__isnull=False,
                    )
                    | Q(
                        vendor_type=VendorType.BUSINESS,
                        business_name__isnull=False,
                        business_address__isnull=False,
                    )
                ),
                name="vendor_type_required_fields",
            ),
        ]

    def __str__(self):
        return self.store_name

    @property
    @extend_schema_field(serializers.BooleanField())
    def is_verified(self):
        return self.status == VendorStatus.VERIFIED


class VendorDocument(BaseModel):
    """DDS §4.4. Single proof-of-studentship document per vendor in MVP."""

    vendor_profile = models.ForeignKey(
        VendorProfile,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(max_length=30, choices=VendorDocumentType.choices)
    file = CloudinaryDocumentField(folder="vendor_documents")
    status = models.CharField(
        max_length=20,
        choices=VendorDocumentStatus.choices,
        default=VendorDocumentStatus.PENDING,
        db_index=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_reviews",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vendor_profile.store_name} — {self.document_type}"
