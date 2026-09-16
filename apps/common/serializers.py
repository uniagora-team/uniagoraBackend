"""DRF integration for Cloudinary-backed model fields.

The registration runs once from `CommonConfig.ready()`.
"""

from cloudinary import CloudinaryResource
from cloudinary.models import CloudinaryField as CloudinaryModelField
from rest_framework import serializers


class CloudinaryFileField(serializers.FileField):
    """Serializes Cloudinary-backed values as absolute URLs; accepts uploads.

    Read side (`to_representation`):
        A `CloudinaryResource` (what the model field returns from the DB) is
        rendered with `resource.url`, which builds the absolute
        `https://res.cloudinary.com/...` URL client-side from the stored
        public_id — no network call and no API-secret involvement. Legacy rows
        whose raw value was an external URL string are reconstructed verbatim
        instead of being mis-parsed into a Cloudinary URL.

    Write side: inherited `FileField` behavior — an uploaded file passes
    through untouched so the model field's `pre_save` performs the Cloudinary
    upload.
    """

    def __init__(self, **kwargs):
        # URL output is unconditional; accept-and-ignore DRF's `use_url` hook.
        kwargs.pop("use_url", None)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not value:
            return None

        if isinstance(value, CloudinaryResource):
            public_id = value.public_id or ""
            if public_id.startswith(("http://", "https://")):
                # Legacy row: the raw DB value was an external URL string and
                # `from_db_value` parsed it into a resource. Rebuild the
                # original URL instead of nesting it inside a Cloudinary URL.
                return f"{public_id}.{value.format}" if value.format else public_id

            return value.url

        # Fallback (e.g. an unsaved file-like object): DRF's stock behavior.
        return super().to_representation(value)


def register_cloudinary_serializer_field_mapping() -> None:
    """Map Cloudinary model fields to `CloudinaryFileField` project-wide.

    Idempotent: safe to call from `AppConfig.ready()` regardless of how many
    times Django initializes the app registry in one process.
    """
    from rest_framework.serializers import ModelSerializer

    mapping = ModelSerializer.serializer_field_mapping
    if mapping.get(CloudinaryModelField) is not CloudinaryFileField:
        mapping[CloudinaryModelField] = CloudinaryFileField
