from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.products.models import Product, ProductCondition, ProductStatus

from .factories import (
    make_admin,
    make_category,
    make_customer,
    make_product,
    make_university,
    make_verified_vendor,
)


class ProductListViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uni_a = make_university(name="University A", short_name="UA")
        cls.uni_b = make_university(name="University B", short_name="UB")
        _, _, cls.store_a = make_verified_vendor(
            cls.uni_a, email="vendor-a@example.com", store_name="Store A"
        )
        _, _, cls.store_b = make_verified_vendor(
            cls.uni_b, email="vendor-b@example.com", store_name="Store B"
        )
        cls.customer_a = make_customer(university=cls.uni_a, email="cust-a@example.com")

        cls.active_a = make_product(
            cls.store_a, cls.uni_a, name="Visible A", status=ProductStatus.ACTIVE
        )
        cls.expired_a = make_product(
            cls.store_a, cls.uni_a, name="Expired A", status=ProductStatus.EXPIRED
        )
        cls.active_b = make_product(
            cls.store_b, cls.uni_b, name="Visible B", status=ProductStatus.ACTIVE
        )

    def test_anonymous_cannot_list(self):
        response = self.client.get(reverse("product-list"))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_customer_sees_only_own_university_active_products(self):
        self.client.force_authenticate(self.customer_a)
        response = self.client.get(reverse("product-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {item["name"] for item in response.data["data"]["results"]}
        self.assertIn("Visible A", names)
        self.assertNotIn("Expired A", names)
        self.assertNotIn("Visible B", names)

    def test_envelope_shape(self):
        self.client.force_authenticate(self.customer_a)
        response = self.client.get(reverse("product-list"))
        self.assertIn("success", response.data)
        self.assertIn("data", response.data)
        self.assertIn("results", response.data["data"])

    def test_price_filter(self):
        self.client.force_authenticate(self.customer_a)
        make_product(
            self.store_a,
            self.uni_a,
            name="Cheap",
            price=Decimal("1.00"),
            status=ProductStatus.ACTIVE,
        )
        response = self.client.get(reverse("product-list"), {"min_price": "500"})
        names = {item["name"] for item in response.data["data"]["results"]}
        self.assertNotIn("Cheap", names)

    def test_condition_filter(self):
        self.client.force_authenticate(self.customer_a)
        make_product(
            self.store_a,
            self.uni_a,
            name="Used Item",
            condition=ProductCondition.USED,
            status=ProductStatus.ACTIVE,
        )
        response = self.client.get(reverse("product-list"), {"condition": "USED"})
        names = {item["name"] for item in response.data["data"]["results"]}
        self.assertIn("Used Item", names)
        self.assertNotIn("Visible A", names)

    def test_invalid_min_price_query_parameter_returns_400(self):
        self.client.force_authenticate(self.customer_a)

        response = self.client.get(
            reverse("product-list"),
            {"min_price": "not-a-number"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("min_price", response.data["errors"])

    def test_invalid_max_price_query_parameter_returns_400(self):
        self.client.force_authenticate(self.customer_a)

        response = self.client.get(
            reverse("product-list"),
            {"max_price": "not-a-number"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("max_price", response.data["errors"])

    def test_invalid_condition_query_parameter_returns_400(self):
        self.client.force_authenticate(self.customer_a)

        response = self.client.get(
            reverse("product-list"),
            {"condition": "REFURBISHED"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("condition", response.data["errors"])

    def test_invalid_ordering_query_parameter_returns_400(self):
        self.client.force_authenticate(self.customer_a)

        response = self.client.get(
            reverse("product-list"),
            {"ordering": "banana"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("ordering", response.data["errors"])

    def test_min_price_greater_than_max_price_returns_400(self):
        self.client.force_authenticate(self.customer_a)

        response = self.client.get(
            reverse("product-list"),
            {
                "min_price": "500.00",
                "max_price": "100.00",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("min_price", response.data["errors"])


class ProductRetrieveViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        cls.vendor_user, cls.vendor_profile, cls.store = make_verified_vendor(
            cls.university
        )
        cls.customer = make_customer(
            university=cls.university, email="cust@example.com"
        )
        cls.other_uni = make_university(name="Other Uni", short_name="OU")
        cls.other_customer = make_customer(
            university=cls.other_uni, email="other@example.com"
        )
        cls.admin = make_admin()

    def test_customer_can_view_active_product_in_own_university(self):
        product = make_product(self.store, self.university, status=ProductStatus.ACTIVE)
        self.client.force_authenticate(self.customer)
        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_customer_cannot_view_expired_product(self):
        product = make_product(
            self.store, self.university, status=ProductStatus.EXPIRED
        )
        self.client.force_authenticate(self.customer)
        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_customer_cannot_view_product_from_other_university(self):
        product = make_product(self.store, self.university, status=ProductStatus.ACTIVE)
        self.client.force_authenticate(self.other_customer)
        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_view_own_expired_product(self):
        product = make_product(
            self.store, self.university, status=ProductStatus.EXPIRED
        )
        self.client.force_authenticate(self.vendor_user)
        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_view_removed_product(self):
        product = make_product(
            self.store, self.university, status=ProductStatus.REMOVED_BY_ADMIN
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_view_count_increments(self):
        product = make_product(self.store, self.university, status=ProductStatus.ACTIVE)
        self.client.force_authenticate(self.customer)
        self.client.get(reverse("product-detail", args=[product.slug]))
        product.refresh_from_db()
        self.assertEqual(product.views_count, 1)

    def test_owner_view_does_not_increment_view_count(self):
        """The vendor previewing their own listing is not counted as a view."""
        product = make_product(self.store, self.university, status=ProductStatus.ACTIVE)
        self.client.force_authenticate(self.vendor_user)
        self.client.get(reverse("product-detail", args=[product.slug]))
        product.refresh_from_db()
        self.assertEqual(product.views_count, 0)

    def test_admin_view_does_not_increment_view_count(self):
        """Admin moderation views do not count as customer interest."""
        product = make_product(self.store, self.university, status=ProductStatus.ACTIVE)
        self.client.force_authenticate(self.admin)
        self.client.get(reverse("product-detail", args=[product.slug]))
        product.refresh_from_db()
        self.assertEqual(product.views_count, 0)

    def test_unknown_slug_returns_404(self):
        self.client.force_authenticate(self.customer)
        response = self.client.get(reverse("product-detail", args=["does-not-exist"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProductCreateViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        (
            cls.vendor_user,
            cls.vendor_profile,
            cls.store,
        ) = make_verified_vendor(cls.university)

        cls.customer = make_customer(
            university=cls.university,
            email="cust@example.com",
        )

    @staticmethod
    def make_primary_image():
        image = Image.new("RGB", (1, 1), color="white")
        image_file = BytesIO()
        image.save(image_file, format="PNG")
        image_file.seek(0)

        return SimpleUploadedFile(
            "primary.png",
            image_file.read(),
            content_type="image/png",
        )

    @staticmethod
    def cloudinary_upload_result():
        return {
            "public_id": "products/test/primary",
            "format": "png",
            "resource_type": "image",
            "type": "upload",
            "version": 1234567890,
            "signature": "test-signature",
            "url": (
                "https://res.cloudinary.com/test/image/upload/"
                "v1234567890/products/test/primary.png"
            ),
            "secure_url": (
                "https://res.cloudinary.com/test/image/upload/"
                "v1234567890/products/test/primary.png"
            ),
        }

    def test_anonymous_cannot_create(self):
        response = self.client.post(
            reverse("product-list"),
            {
                "name": "X",
                "price": "1.00",
                "condition": ProductCondition.NEW,
            },
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )

    def test_plain_customer_cannot_create(self):
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            reverse("product-list"),
            {
                "name": "X",
                "price": "1.00",
                "condition": ProductCondition.NEW,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("cloudinary.uploader.upload")
    def test_verified_vendor_can_create_with_primary_image(
        self,
        mock_upload,
    ):
        mock_upload.return_value = self.cloudinary_upload_result()

        self.client.force_authenticate(self.vendor_user)

        response = self.client.post(
            reverse("product-list"),
            {
                "name": "Brand New Item",
                "price": "42.00",
                "condition": ProductCondition.NEW,
                "primary_image": self.make_primary_image(),
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["data"]["store"]["id"],
            str(self.store.id),
        )

        self.assertEqual(
            len(response.data["data"]["images"]),
            1,
        )

        self.assertTrue(
            response.data["data"]["images"][0]["is_primary"],
        )

        image = Product.objects.get(
            slug=response.data["data"]["slug"],
        ).images.get()

        self.assertEqual(
            image.image.public_id,
            "products/test/primary",
        )

        self.assertEqual(
            image.image.format,
            "png",
        )

        mock_upload.assert_called_once()

    @patch("cloudinary.uploader.upload")
    def test_created_product_has_active_status_regardless_of_input(
        self,
        mock_upload,
    ):
        mock_upload.return_value = self.cloudinary_upload_result()

        self.client.force_authenticate(self.vendor_user)

        response = self.client.post(
            reverse("product-list"),
            {
                "name": "X",
                "price": "1.00",
                "condition": ProductCondition.NEW,
                "status": ProductStatus.REMOVED_BY_ADMIN,
                "primary_image": self.make_primary_image(),
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["data"]["status"],
            ProductStatus.ACTIVE,
        )

    def test_invalid_payload_rejected(self):
        self.client.force_authenticate(self.vendor_user)

        response = self.client.post(
            reverse("product-list"),
            {
                "price": "1.00",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_verified_vendor_cannot_create_without_primary_image(self):
        self.client.force_authenticate(self.vendor_user)

        response = self.client.post(
            reverse("product-list"),
            {
                "name": "Image-less Listing",
                "price": "42.00",
                "condition": ProductCondition.NEW,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "primary_image",
            response.data["errors"],
        )


class ProductCategoriesViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        cls.vendor_user, cls.vendor_profile, cls.store = make_verified_vendor(
            cls.university
        )
        cls.category = make_category()

    def test_owner_can_assign_categories(self):
        product = make_product(self.store, self.university)
        self.client.force_authenticate(self.vendor_user)
        response = self.client.put(
            reverse("product-categories", args=[product.slug]),
            {"category_ids": [str(self.category.id)]},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["categories"]), 1)


class ProductAdminModerationViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        cls.vendor_user, cls.vendor_profile, cls.store = make_verified_vendor(
            cls.university
        )
        cls.admin = make_admin()

    def test_admin_can_remove_listing(self):
        product = make_product(self.store, self.university, status=ProductStatus.ACTIVE)
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("product-remove-listing", args=[product.slug])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["data"]["status"], ProductStatus.REMOVED_BY_ADMIN
        )

    def test_vendor_cannot_remove_listing(self):
        product = make_product(self.store, self.university, status=ProductStatus.ACTIVE)
        self.client.force_authenticate(self.vendor_user)
        response = self.client.post(
            reverse("product-remove-listing", args=[product.slug])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_removing_already_removed_listing_returns_409(self):
        product = make_product(
            self.store, self.university, status=ProductStatus.REMOVED_BY_ADMIN
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("product-remove-listing", args=[product.slug])
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class ProductMineViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        cls.vendor_user, cls.vendor_profile, cls.store = make_verified_vendor(
            cls.university
        )

    def test_mine_returns_all_own_statuses(self):
        make_product(
            self.store, self.university, name="Active", status=ProductStatus.ACTIVE
        )
        make_product(
            self.store, self.university, name="Expired", status=ProductStatus.EXPIRED
        )
        self.client.force_authenticate(self.vendor_user)
        response = self.client.get(reverse("product-mine"))
        names = {item["name"] for item in response.data["data"]["results"]}
        self.assertEqual(names, {"Active", "Expired"})

    def test_mine_route_does_not_collide_with_slug_lookup(self):
        """Regression for the exact class of bug already fixed in `stores`
        (SimpleRouter route-ordering for detail=False actions vs. slug
        lookup)."""
        self.client.force_authenticate(self.vendor_user)
        response = self.client.get(reverse("product-mine"))
        self.assertNotEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProductImageViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = make_university()
        cls.vendor_user, cls.vendor_profile, cls.store = make_verified_vendor(
            cls.university
        )
        cls.other_vendor_user, cls.other_vendor_profile, cls.other_store = (
            make_verified_vendor(
                cls.university,
                email="other-vendor@example.com",
                store_name="Other Store",
                matric_number="MAT/9997",
            )
        )

    def test_owner_can_list_images(self):
        product = make_product(self.store, self.university)
        self.client.force_authenticate(self.vendor_user)
        response = self.client.get(reverse("product-images", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_owner_cannot_list_images(self):
        product = make_product(self.store, self.university)
        self.client.force_authenticate(self.other_vendor_user)
        response = self.client.get(reverse("product-images", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
