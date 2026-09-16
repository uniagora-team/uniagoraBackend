from rest_framework import serializers

from apps.common.fields import (
    validate_document_content_type,
    validate_image_content_type,
    validate_upload_size,
)
from apps.common.serializers import CloudinaryFileField
from apps.universities.models import University
from apps.universities.serializers import UniversitySerializer

from .models import VendorDocument, VendorDocumentType, VendorProfile, VendorType


class VendorDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorDocument
        fields = ["id", "document_type", "file", "status", "uploaded_at", "reviewed_at"]
        read_only_fields = fields


class VendorProfileSerializer(serializers.ModelSerializer):
    """Read-only. Used for every response body (list/retrieve/create/
    activate-style actions)"""

    university = UniversitySerializer(read_only=True)
    reviewed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    documents = VendorDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = VendorProfile
        fields = [
            "id",
            "user",
            "university",
            "vendor_type",
            "store_name",
            "phone_number",
            "matric_number",
            "department",
            "level",
            "business_name",
            "business_address",
            "business_logo",
            "status",
            "is_verified",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "documents",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VendorApplicationSerializer(serializers.ModelSerializer):
    university = serializers.PrimaryKeyRelatedField(
        queryset=University.objects.active()
    )
    document_type = serializers.ChoiceField(
        choices=VendorDocumentType.choices, required=False, allow_null=True
    )
    document_file = serializers.FileField(
        required=False,
        allow_null=True,
        validators=[validate_upload_size, validate_document_content_type],
    )
    # Accept an uploaded image file — never a client-supplied URL string.
    # Validators enforce the shared 8MB / image-type policy (Architecture §10).
    business_logo = CloudinaryFileField(
        required=False,
        allow_null=True,
        validators=[validate_upload_size, validate_image_content_type],
    )

    class Meta:
        model = VendorProfile
        fields = [
            "university",
            "vendor_type",
            "store_name",
            "phone_number",
            "matric_number",
            "department",
            "level",
            "business_name",
            "business_address",
            "business_logo",
            "document_type",
            "document_file",
        ]
        validators = []

    def validate(self, attrs):
        vendor_type = attrs.get("vendor_type")
        errors = {}

        if vendor_type == VendorType.STUDENT:
            for field in ("matric_number", "department", "level"):
                if not attrs.get(field):
                    errors[field] = "Required for student vendors."

            if not attrs.get("document_type") or not attrs.get("document_file"):
                errors["document_type"] = (
                    "A proof-of-studentship document is required for student vendors."
                )
            elif attrs["document_type"] == VendorDocumentType.BUSINESS_DOCUMENT:
                errors["document_type"] = "Invalid document type for a student vendor."

            matric_number = attrs.get("matric_number")
            university = attrs.get("university")
            if (
                matric_number
                and university
                and VendorProfile.objects.alive()
                .filter(university=university, matric_number=matric_number)
                .exists()
            ):
                errors["matric_number"] = (
                    "This matric number is already registered at this university."
                )

        elif vendor_type == VendorType.BUSINESS:
            for field in ("business_name", "business_address"):
                if not attrs.get(field):
                    errors[field] = "Required for business vendors."
        else:
            errors["vendor_type"] = "Must be STUDENT or BUSINESS."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs
