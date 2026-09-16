from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.categories.models import Category
from apps.common.fields import validate_image_content_type, validate_upload_size

from .models import Product, ProductCondition, ProductImage


def _reject_duplicate_category_ids(value):
    if len(value) != len(set(value)):
        raise serializers.ValidationError("Duplicate category IDs are not allowed.")


class CategoryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]
        read_only_fields = fields


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "is_primary",
            "display_order",
        ]
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    store = serializers.SerializerMethodField()
    university = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()

    condition_display = serializers.CharField(
        source="get_condition_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "slug",
            "name",
            "description",
            "price",
            "condition",
            "condition_display",
            "quantity",
            "availability",
            "campus_location",
            "status",
            "status_display",
            "views_count",
            "listed_at",
            "expires_at",
            "store",
            "university",
            "categories",
            "images",
            "primary_image",
        ]
        read_only_fields = fields

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "format": "uuid",
                },
                "vendor_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": (
                        "Owning VendorProfile id — the identifier clients supply "
                        "to initiate a conversation or report the vendor."
                    ),
                },
                "slug": {
                    "type": "string",
                },
                "display_name": {
                    "type": "string",
                },
            },
            "required": [
                "id",
                "vendor_id",
                "slug",
                "display_name",
            ],
        }
    )
    def get_store(self, obj):
        return {
            "id": str(obj.store_id),
            "vendor_id": str(obj.store.vendor_profile_id),
            "slug": obj.store.slug,
            "display_name": obj.store.display_name,
        }

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "format": "uuid",
                },
                "name": {
                    "type": "string",
                },
                "short_name": {
                    "type": "string",
                },
            },
            "required": [
                "id",
                "name",
                "short_name",
            ],
        }
    )
    def get_university(self, obj):
        return {
            "id": str(obj.university_id),
            "name": obj.university.name,
            "short_name": obj.university.short_name,
        }

    @extend_schema_field(CategoryBriefSerializer(many=True))
    def get_categories(self, obj):
        links = obj.category_links.select_related("category").filter(
            category__is_active=True
        )

        return CategoryBriefSerializer(
            [link.category for link in links],
            many=True,
        ).data

    @extend_schema_field(ProductImageSerializer(many=True))
    def get_images(self, obj):
        images = obj.images.alive().order_by("display_order")

        return ProductImageSerializer(
            images,
            many=True,
        ).data

    @extend_schema_field(
        ProductImageSerializer(allow_null=True),
    )
    def get_primary_image(self, obj):
        image = obj.primary_image

        return ProductImageSerializer(image).data if image else None

    @extend_schema_field(
        {
            "type": "string",
            "enum": [
                "IN_STOCK",
                "OUT_OF_STOCK",
            ],
        }
    )
    def get_availability(self, obj):
        return "OUT_OF_STOCK" if obj.is_out_of_stock else "IN_STOCK"


class ProductCreateSerializer(serializers.Serializer):
    """Client input for product creation.

    A primary image is required at creation time because the PRD/DDS require
    every persisted listing to have at least one image and exactly one
    primary image.
    """

    name = serializers.CharField(max_length=200)

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
    )

    condition = serializers.ChoiceField(
        choices=ProductCondition.choices,
    )

    quantity = serializers.IntegerField(
        required=False,
        min_value=0,
        default=1,
    )

    campus_location = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=150,
    )

    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        validators=[_reject_duplicate_category_ids],
    )

    primary_image = serializers.ImageField(
        required=True,
        validators=[validate_upload_size, validate_image_content_type],
    )


class ProductUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=200,
        required=False,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
    )

    condition = serializers.ChoiceField(
        choices=ProductCondition.choices,
        required=False,
    )

    campus_location = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=150,
    )

    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        validators=[_reject_duplicate_category_ids],
    )


class ProductListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    category = serializers.SlugField(
        required=False,
        allow_blank=True,
    )

    min_price = serializers.DecimalField(
        required=False,
        min_value=Decimal("0"),
        max_digits=10,
        decimal_places=2,
    )

    max_price = serializers.DecimalField(
        required=False,
        min_value=Decimal("0"),
        max_digits=10,
        decimal_places=2,
    )

    condition = serializers.ChoiceField(
        required=False,
        choices=ProductCondition.choices,
    )

    ordering = serializers.ChoiceField(
        required=False,
        choices=(
            ("newest", "Newest"),
            ("price_asc", "Lowest Price"),
            ("price_desc", "Highest Price"),
        ),
    )

    def validate(self, attrs):
        min_price = attrs.get("min_price")
        max_price = attrs.get("max_price")

        if min_price is not None and max_price is not None and min_price > max_price:
            raise serializers.ValidationError(
                {"min_price": ("min_price must be less than or equal to max_price.")}
            )

        return attrs


class InventoryUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(
        min_value=0,
    )


class ProductCategoryAssignmentSerializer(serializers.Serializer):
    """Full-replace category assignment payload for PUT .../categories/."""

    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        validators=[_reject_duplicate_category_ids],
    )


class ProductImageUploadSerializer(serializers.Serializer):
    image = serializers.ImageField(
        validators=[validate_upload_size, validate_image_content_type],
    )

    is_primary = serializers.BooleanField(
        required=False,
    )

    display_order = serializers.IntegerField(
        required=False,
        min_value=0,
    )
