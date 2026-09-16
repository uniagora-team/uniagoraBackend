from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.products.models import ProductCondition, ProductImage, ProductStatus
from apps.products.search.filters import (
    apply_category_filter,
    apply_condition_filter,
    apply_ordering,
    apply_price_filter,
)
from apps.products.search.queries import apply_keyword_search
from apps.products.serializers import (
    ProductCreateSerializer,
    ProductImageSerializer,
    ProductListQuerySerializer,
    ProductSerializer,
    ProductUpdateSerializer,
)

from .factories import (
    make_category,
    make_product,
    make_university,
    make_verified_vendor,
)


class ProductSerializerReadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        _, cls.vendor_profile, cls.store = make_verified_vendor(cls.university)
        cls.category = make_category()

    def test_read_serializer_includes_expected_fields(self):
        product = make_product(self.store, self.university)
        data = ProductSerializer(product).data
        for field in (
            "id",
            "slug",
            "name",
            "description",
            "price",
            "condition",
            "quantity",
            "availability",
            "status",
            "listed_at",
            "expires_at",
            "store",
            "university",
            "categories",
            "images",
            "primary_image",
        ):
            self.assertIn(field, data)

    def test_read_serializer_includes_current_status(self):
        """The read serializer's `status` is a plain output field — there is
        no serializer anywhere in this app that accepts `status` as input
        (verified in the write-serializer tests below)."""
        product = make_product(self.store, self.university)
        data = ProductSerializer(product).data
        self.assertEqual(data["status"], ProductStatus.ACTIVE)

    def test_store_object_includes_vendor_id(self):
        """The storefront's route to a VendorProfile id for chat/report
        initiation rides along on every product payload."""
        product = make_product(self.store, self.university)
        data = ProductSerializer(product).data
        self.assertEqual(
            str(data["store"]["vendor_id"]),
            str(self.vendor_profile.id),
        )

    def test_availability_reflected_in_output(self):
        product = make_product(
            self.store,
            self.university,
            quantity=0,
        )
        data = ProductSerializer(product).data
        self.assertEqual(
            data["availability"],
            "OUT_OF_STOCK",
        )

    def test_availability_reflects_in_stock_state(self):
        product = make_product(
            self.store,
            self.university,
            quantity=5,
        )
        data = ProductSerializer(product).data
        self.assertEqual(
            data["availability"],
            "IN_STOCK",
        )

    def test_categories_only_include_active_categories(self):
        from apps.products.models import ProductCategory

        inactive = make_category(name="Inactive Cat", is_active=False)
        product = make_product(self.store, self.university)
        ProductCategory.objects.create(product=product, category=self.category)
        ProductCategory.objects.create(product=product, category=inactive)
        data = ProductSerializer(product).data
        names = {c["name"] for c in data["categories"]}
        self.assertIn(self.category.name, names)
        self.assertNotIn(inactive.name, names)

    def test_images_serialized_in_display_order(self):
        product = make_product(self.store, self.university)
        ProductImage.objects.create(
            product=product, image="b.jpg", is_primary=False, display_order=1
        )
        ProductImage.objects.create(
            product=product, image="a.jpg", is_primary=True, display_order=0
        )
        data = ProductSerializer(product).data
        self.assertEqual(len(data["images"]), 2)
        self.assertTrue(data["images"][0]["is_primary"])

    def test_primary_image_null_when_no_images(self):
        product = make_product(self.store, self.university)
        data = ProductSerializer(product).data
        self.assertIsNone(data["primary_image"])


class ProductCreateSerializerTests(TestCase):
    @staticmethod
    def make_primary_image():
        buffer = BytesIO()

        image = Image.new("RGB", (1, 1), "white")
        image.save(buffer, format="PNG")
        buffer.seek(0)

        return SimpleUploadedFile(
            "primary.png",
            buffer.read(),
            content_type="image/png",
        )

    def test_valid_payload_accepted(self):
        serializer = ProductCreateSerializer(
            data={
                "name": "New Item",
                "price": "25.00",
                "condition": ProductCondition.NEW,
                "primary_image": self.make_primary_image(),
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_missing_primary_image_rejected(self):
        serializer = ProductCreateSerializer(
            data={
                "name": "New Item",
                "price": "25.00",
                "condition": ProductCondition.NEW,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("primary_image", serializer.errors)

    def test_missing_required_field_rejected(self):
        serializer = ProductCreateSerializer(
            data={
                "price": "25.00",
                "condition": ProductCondition.NEW,
                "primary_image": self.make_primary_image(),
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)

    def test_negative_price_rejected(self):
        serializer = ProductCreateSerializer(
            data={
                "name": "X",
                "price": "-1.00",
                "condition": ProductCondition.NEW,
                "primary_image": self.make_primary_image(),
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("price", serializer.errors)

    def test_invalid_condition_rejected(self):
        serializer = ProductCreateSerializer(
            data={
                "name": "X",
                "price": "1.00",
                "condition": "REFURBISHED",
                "primary_image": self.make_primary_image(),
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("condition", serializer.errors)

    def test_status_field_not_accepted(self):
        """`status` has no field on the create serializer at all — supplying
        it is silently ignored, never validated as an override.
        """
        serializer = ProductCreateSerializer(
            data={
                "name": "X",
                "price": "1.00",
                "condition": ProductCondition.NEW,
                "primary_image": self.make_primary_image(),
                "status": ProductStatus.REMOVED_BY_ADMIN,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("status", serializer.validated_data)

    def test_university_field_not_accepted(self):
        serializer = ProductCreateSerializer(
            data={
                "name": "X",
                "price": "1.00",
                "condition": ProductCondition.NEW,
                "primary_image": self.make_primary_image(),
                "university": "11111111-1111-1111-1111-111111111111",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("university", serializer.validated_data)

    def test_default_quantity_is_one(self):
        serializer = ProductCreateSerializer(
            data={
                "name": "X",
                "price": "1.00",
                "condition": ProductCondition.NEW,
                "primary_image": self.make_primary_image(),
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["quantity"], 1)


class ProductUpdateSerializerTests(TestCase):
    def test_quantity_field_does_not_exist(self):
        self.assertNotIn("quantity", ProductUpdateSerializer().fields)

    def test_partial_update_accepts_single_field(self):
        serializer = ProductUpdateSerializer(data={"price": "99.00"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(set(serializer.validated_data.keys()), {"price"})


class ProductListQuerySerializerTests(TestCase):
    def test_valid_query_parameters_are_accepted(self):
        serializer = ProductListQuerySerializer(
            data={
                "q": "laptop",
                "category": "electronics",
                "min_price": "100.00",
                "max_price": "500.00",
                "condition": ProductCondition.USED,
                "ordering": "price_asc",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        self.assertEqual(
            serializer.validated_data["min_price"],
            Decimal("100.00"),
        )
        self.assertEqual(
            serializer.validated_data["max_price"],
            Decimal("500.00"),
        )
        self.assertEqual(
            serializer.validated_data["condition"],
            ProductCondition.USED,
        )

    def test_query_parameters_are_optional(self):
        serializer = ProductListQuerySerializer(data={})

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_min_price_is_rejected(self):
        serializer = ProductListQuerySerializer(
            data={
                "min_price": "not-a-number",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("min_price", serializer.errors)

    def test_invalid_max_price_is_rejected(self):
        serializer = ProductListQuerySerializer(
            data={
                "max_price": "not-a-number",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("max_price", serializer.errors)

    def test_negative_min_price_is_rejected(self):
        serializer = ProductListQuerySerializer(
            data={
                "min_price": "-1.00",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("min_price", serializer.errors)

    def test_negative_max_price_is_rejected(self):
        serializer = ProductListQuerySerializer(
            data={
                "max_price": "-1.00",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("max_price", serializer.errors)

    def test_min_price_cannot_exceed_max_price(self):
        serializer = ProductListQuerySerializer(
            data={
                "min_price": "500.00",
                "max_price": "100.00",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("min_price", serializer.errors)

    def test_invalid_condition_is_rejected(self):
        serializer = ProductListQuerySerializer(
            data={
                "condition": "REFURBISHED",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("condition", serializer.errors)

    def test_invalid_ordering_is_rejected(self):
        serializer = ProductListQuerySerializer(
            data={
                "ordering": "banana",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("ordering", serializer.errors)

    def test_valid_orderings_are_accepted(self):
        for ordering in (
            "newest",
            "price_asc",
            "price_desc",
        ):
            serializer = ProductListQuerySerializer(
                data={"ordering": ordering},
            )

            self.assertTrue(
                serializer.is_valid(),
                serializer.errors,
            )


class SearchFilterHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        _, cls.vendor_profile, cls.store = make_verified_vendor(cls.university)
        cls.category = make_category()

    def test_price_filter_applies_min_and_max(self):
        from apps.products.models import Product

        make_product(self.store, self.university, name="Cheap", price=Decimal("5.00"))
        make_product(self.store, self.university, name="Mid", price=Decimal("50.00"))
        make_product(
            self.store, self.university, name="Expensive", price=Decimal("500.00")
        )
        qs = apply_price_filter(
            Product.objects.visible(),
            min_price=Decimal("10.00"),
            max_price=Decimal("100.00"),
        )
        self.assertEqual(set(qs.values_list("name", flat=True)), {"Mid"})

    def test_condition_filter(self):
        from apps.products.models import Product

        make_product(
            self.store, self.university, name="New One", condition=ProductCondition.NEW
        )
        make_product(
            self.store,
            self.university,
            name="Used One",
            condition=ProductCondition.USED,
        )
        qs = apply_condition_filter(Product.objects.visible(), ProductCondition.USED)
        self.assertEqual(set(qs.values_list("name", flat=True)), {"Used One"})

    def test_category_filter(self):
        from apps.products.models import Product, ProductCategory

        matching = make_product(self.store, self.university, name="Matches")
        make_product(self.store, self.university, name="No Match")
        ProductCategory.objects.create(product=matching, category=self.category)
        qs = apply_category_filter(Product.objects.visible(), self.category.slug)
        self.assertEqual(set(qs.values_list("name", flat=True)), {"Matches"})

    def test_ordering_newest_default(self):
        from apps.products.models import Product

        qs = apply_ordering(Product.objects.visible(), None)
        self.assertEqual(qs.query.order_by, ("-listed_at",))

    def test_ordering_price_ascending(self):
        from apps.products.models import Product

        qs = apply_ordering(Product.objects.visible(), "price_asc")
        self.assertEqual(qs.query.order_by, ("price",))

    def test_keyword_search_matches_name(self):
        from apps.products.models import Product

        make_product(
            self.store,
            self.university,
            name="Vintage Calculator",
            description="Works great",
        )
        make_product(
            self.store,
            self.university,
            name="Office Chair",
            description="Comfortable seating",
        )
        qs = apply_keyword_search(Product.objects.visible(), "calculator")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().name, "Vintage Calculator")

    def test_keyword_search_noop_when_empty(self):
        from apps.products.models import Product

        make_product(self.store, self.university)
        base_count = Product.objects.visible().count()
        qs = apply_keyword_search(Product.objects.visible(), "")
        self.assertEqual(qs.count(), base_count)


class ProductImageURLSerializationTests(TestCase):
    """Regression guard: Cloudinary-backed ``image`` fields must serialize as
    absolute https://res.cloudinary.com/... URLs, never raw DB strings
    ("image/upload/v.../<public_id>"). Enforced project-wide by the
    Cloudinary -> DRF field mapping in apps/common/serializers.py."""

    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        _, _, cls.store = make_verified_vendor(cls.university)

    def test_image_url_is_absolute_cloudinary_url(self):
        product = make_product(self.store, self.university)
        ProductImage.objects.create(product=product, image="regression.jpg")

        image = ProductImage.objects.alive().first()
        data = ProductImageSerializer(image).data

        url = data["image"]
        self.assertIsInstance(url, str)
        self.assertTrue(url.startswith("https://res.cloudinary.com/"))
        self.assertIn("/image/upload/", url)
        self.assertIn("regression.jpg", url)

    def test_primary_image_url_is_absolute_when_present(self):
        product = make_product(self.store, self.university)
        ProductImage.objects.create(
            product=product, image="primary.jpg", is_primary=True
        )

        data = ProductSerializer(product).data

        self.assertIsNotNone(data["primary_image"])
        url = data["primary_image"]["image"]
        self.assertTrue(url.startswith("https://res.cloudinary.com/"))
