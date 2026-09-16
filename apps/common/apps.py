from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"

    def ready(self) -> None:
        # Register the Cloudinary -> DRF field mapping once, project-wide, so
        # every ModelSerializer renders Cloudinary-backed fields as absolute
        # URLs (see apps.common.serializers for details).
        from apps.common.serializers import register_cloudinary_serializer_field_mapping

        register_cloudinary_serializer_field_mapping()
