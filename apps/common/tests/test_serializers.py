from cloudinary.models import CloudinaryField as CloudinaryModelField
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.serializers import ModelSerializer
from rest_framework.utils.field_mapping import ClassLookupDict

from apps.common.fields import CloudinaryDocumentField, CloudinaryImageField
from apps.common.serializers import (
    CloudinaryFileField,
    register_cloudinary_serializer_field_mapping,
)


class CloudinaryFileFieldTests(SimpleTestCase):
    """Unit tests for the Cloudinary-aware DRF field."""

    def _field(self):
        return CloudinaryFileField()

    def _resource(self, raw):
        return CloudinaryModelField().parse_cloudinary_resource(raw)

    def test_resource_serializes_to_absolute_cloudinary_url(self):
        value = self._resource("image/upload/v1757900000/products/x.jpg")

        url = self._field().to_representation(value)

        self.assertTrue(url.startswith("https://res.cloudinary.com/"))
        self.assertIn("/image/upload/v1757900000/products/x.jpg", url)

    def test_none_and_empty_represent_as_null(self):
        self.assertIsNone(self._field().to_representation(None))
        self.assertIsNone(self._field().to_representation(""))

    def test_raw_unparsed_string_represents_as_null(self):
        """Unparsed raw values (e.g. an in-memory instance never round-tripped
        through the DB) render as null — same contract as DRF's stock
        FileField for values without a usable ``.url``. API responses are
        unaffected because every write path stores a parsed resource or None.
        """
        self.assertIsNone(self._field().to_representation("a.jpg"))

    def test_legacy_url_parsed_into_resource_is_reconstructed(self):
        """A legacy row stored as an external URL string is re-emitted
        verbatim instead of being nested inside a Cloudinary URL."""
        raw = "https://example.com/logo.png"
        resource = self._resource(raw)

        self.assertEqual(self._field().to_representation(resource), raw)

    def test_fallback_delegates_to_filefield_for_file_like_values(self):
        # DRF's stock FileField can only render objects exposing `.url`;
        # an unsaved upload without one represents as None.
        uploaded = SimpleUploadedFile("x.png", b"x", content_type="image/png")

        self.assertIsNone(self._field().to_representation(uploaded))


class CloudinaryFieldMappingTests(SimpleTestCase):
    def test_base_field_is_mapped_after_registration(self):
        register_cloudinary_serializer_field_mapping()

        self.assertIs(
            ModelSerializer.serializer_field_mapping[CloudinaryModelField],
            CloudinaryFileField,
        )

    def test_subclasses_resolve_to_cloudinary_file_field(self):
        register_cloudinary_serializer_field_mapping()
        lookup = ClassLookupDict(ModelSerializer.serializer_field_mapping)

        for model_field_cls in (CloudinaryImageField, CloudinaryDocumentField):
            instance = model_field_cls()
            self.assertIs(lookup[instance], CloudinaryFileField)

    def test_registration_is_idempotent(self):
        register_cloudinary_serializer_field_mapping()
        register_cloudinary_serializer_field_mapping()

        self.assertIs(
            ModelSerializer.serializer_field_mapping[CloudinaryModelField],
            CloudinaryFileField,
        )
