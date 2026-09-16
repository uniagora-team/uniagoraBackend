from rest_framework import serializers

from apps.common.fields import validate_image_content_type, validate_upload_size
from apps.common.serializers import CloudinaryFileField

from .models import University


class UniversitySerializer(serializers.ModelSerializer):
    """Public/customer-facing representation."""

    class Meta:
        model = University
        fields = [
            "id",
            "name",
            "short_name",
            "slug",
            "logo",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class UniversityAdminWriteSerializer(serializers.ModelSerializer):
    # Accept an uploaded image file — never a client-supplied URL string.
    # Validators enforce the shared 8MB / jpeg-png-webp policy (Architecture §10).
    logo = CloudinaryFileField(
        required=False,
        allow_null=True,
        validators=[validate_upload_size, validate_image_content_type],
    )

    class Meta:
        model = University
        fields = ["name", "short_name", "logo"]
