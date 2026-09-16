from django.db.models import F
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import NotFoundError
from apps.common.openapi import (
    paginated_response_schema,
    success_response_schema,
)
from apps.common.response import success_response
from apps.core.filters import ActiveUniversityFilterBackend
from apps.core.permissions import (
    IsAdmin,
    IsAuthenticatedCustomer,
    IsOwnerVendor,
    IsVerifiedVendor,
)

from .models import Product, ProductStatus
from .search.filters import (
    apply_category_filter,
    apply_condition_filter,
    apply_ordering,
    apply_price_filter,
)
from .search.queries import apply_keyword_search
from .serializers import (
    InventoryUpdateSerializer,
    ProductCategoryAssignmentSerializer,
    ProductCreateSerializer,
    ProductImageSerializer,
    ProductImageUploadSerializer,
    ProductListQuerySerializer,
    ProductSerializer,
    ProductUpdateSerializer,
)
from .services import (
    InventoryService,
    ProductImageService,
    ProductLifecycleService,
    ProductService,
)
from .services.product_service import UNSET

_VENDOR_OWNED_ACTIONS = (
    "update",
    "partial_update",
    "destroy",
    "renew",
    "inventory",
    "categories",
)


class ProductViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    lookup_field = "slug"
    filter_backends = [ActiveUniversityFilterBackend]

    # -- Queryset / filtering -------------------------------------------------

    def get_queryset(self):
        if self.action == "list":
            return (
                Product.objects.visible()
                .select_related("store", "university")
                .prefetch_related("images", "category_links__category")
            )

        return Product.objects.alive().select_related(
            "store__vendor_profile",
            "university",
        )

    def filter_queryset(self, queryset):
        """Apply university scoping and validated marketplace filters."""
        if self.action != "list":
            return queryset

        for backend in self.filter_backends:
            queryset = backend().filter_queryset(
                self.request,
                queryset,
                self,
            )

        query_serializer = ProductListQuerySerializer(
            data=self.request.query_params,
        )
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        keyword = params.get("q")

        if keyword:
            queryset = apply_keyword_search(
                queryset,
                keyword,
            )

        queryset = apply_category_filter(
            queryset,
            params.get("category"),
        )

        queryset = apply_price_filter(
            queryset,
            params.get("min_price"),
            params.get("max_price"),
        )

        queryset = apply_condition_filter(
            queryset,
            params.get("condition"),
        )

        if not keyword:
            queryset = apply_ordering(
                queryset,
                params.get("ordering"),
            )

        return queryset

    # -- Permissions / serializer selection ----------------------------------

    def get_permissions(self):
        if self.action in ("create", "mine"):
            return [IsVerifiedVendor()]

        if self.action in _VENDOR_OWNED_ACTIONS:
            return [IsVerifiedVendor(), IsOwnerVendor()]

        if self.action == "remove_listing":
            return [IsAdmin()]

        return [IsAuthenticatedCustomer()]

    def get_serializer_class(self):
        if self.action == "create":
            return ProductCreateSerializer

        if self.action in ("update", "partial_update"):
            return ProductUpdateSerializer

        return ProductSerializer

    # -- Customer marketplace -------------------------------------------------

    @extend_schema(
        parameters=[ProductListQuerySerializer],
        responses={
            200: paginated_response_schema(
                "ProductListResponse",
                ProductSerializer,
            ),
        },
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = ProductSerializer(page, many=True)

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        responses={
            200: success_response_schema(
                "ProductDetailResponse",
                ProductSerializer,
            ),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        """Visible to:

        (a) any authenticated customer, if ACTIVE and in the requester's
            active_university,
        (b) the owning vendor, any status,
        (c) an admin, any status.

        This is a custom visibility rule, not expressible as a single DRF
        permission/filter composition, so it is implemented directly here
        rather than via `get_object()`.
        """
        product = self._resolve_for_retrieve(
            request,
            kwargs["slug"],
        )

        # View counting: only genuine customer interest increments the
        # counter. Owner previews and admin moderation views are excluded so
        # `views_count` reflects external demand rather than vendor/admin
        # self-activity (the vendor sees their own listing while editing,
        # admins while moderating — inflating the metric otherwise).
        viewer = request.user
        viewer_vendor_profile = getattr(viewer, "vendor_profile", None)
        is_owner_view = viewer_vendor_profile is not None and (
            product.store.vendor_profile_id == viewer_vendor_profile.id
        )
        viewer_is_admin = viewer.is_authenticated and viewer.is_admin
        if not (viewer_is_admin or is_owner_view):
            Product.objects.filter(pk=product.pk).update(
                views_count=F("views_count") + 1,
            )
            product.views_count += 1

        return success_response(
            data=ProductSerializer(product).data,
        )

    def _resolve_for_retrieve(self, request, slug):
        try:
            product = (
                Product.objects.alive()
                .select_related(
                    "store__vendor_profile",
                    "university",
                )
                .get(slug=slug)
            )
        except Product.DoesNotExist:
            raise NotFoundError("Product not found.") from None

        user = request.user

        is_admin = user.is_authenticated and (user.is_staff or user.is_superuser)

        is_owner = (
            user.is_authenticated
            and hasattr(user, "vendor_profile")
            and product.store.vendor_profile_id == user.vendor_profile.id
        )

        if is_admin or is_owner:
            return product

        if not user.is_authenticated:
            raise NotFoundError("Product not found.")

        if product.status != ProductStatus.ACTIVE:
            raise NotFoundError("Product not found.")

        if user.active_university_id != product.university_id:
            raise NotFoundError("Product not found.")

        return product

    # -- Vendor product management -------------------------------------------

    @extend_schema(
        request=ProductCreateSerializer,
        responses={
            201: success_response_schema(
                "ProductCreateResponse",
                ProductSerializer,
            ),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = ProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = ProductService.create(
            vendor_profile=request.user.vendor_profile,
            **serializer.validated_data,
        )

        return success_response(
            data=ProductSerializer(product).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=ProductUpdateSerializer,
        responses={
            200: success_response_schema(
                "ProductUpdateResponse",
                ProductSerializer,
            ),
        },
    )
    def update(self, request, *args, **kwargs):
        product = self.get_object()

        serializer = ProductUpdateSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        product = ProductService.update(
            product=product,
            name=data.get("name", UNSET),
            description=data.get("description", UNSET),
            price=data.get("price", UNSET),
            condition=data.get("condition", UNSET),
            campus_location=data.get("campus_location", UNSET),
            category_ids=data.get("category_ids", UNSET),
        )

        return success_response(
            data=ProductSerializer(product).data,
        )

    @extend_schema(
        request=ProductUpdateSerializer,
        responses={
            200: success_response_schema(
                "ProductPartialUpdateResponse",
                ProductSerializer,
            ),
        },
    )
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @extend_schema(
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        product = self.get_object()

        ProductService.delete(product=product)

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )

    @extend_schema(
        responses={
            200: paginated_response_schema(
                "ProductMineResponse",
                ProductSerializer,
            ),
        },
    )
    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        queryset = (
            self.get_queryset()
            .filter(
                store__vendor_profile=request.user.vendor_profile,
            )
            .order_by("-created_at")
        )

        page = self.paginate_queryset(queryset)
        serializer = ProductSerializer(page, many=True)

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=None,
        responses={
            200: success_response_schema(
                "ProductRenewResponse",
                ProductSerializer,
            ),
        },
    )
    @action(detail=True, methods=["post"], url_path="renew")
    def renew(self, request, slug=None):
        product = self.get_object()

        product = ProductLifecycleService.renew(
            product=product,
        )

        return success_response(
            data=ProductSerializer(product).data,
        )

    @extend_schema(
        request=InventoryUpdateSerializer,
        responses={
            200: success_response_schema(
                "ProductInventoryUpdateResponse",
                ProductSerializer,
            ),
        },
    )
    @action(detail=True, methods=["patch"], url_path="inventory")
    def inventory(self, request, slug=None):
        product = self.get_object()

        serializer = InventoryUpdateSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        product = InventoryService.set_quantity(
            product=product,
            quantity=serializer.validated_data["quantity"],
        )

        return success_response(
            data=ProductSerializer(product).data,
        )

    @extend_schema(
        request=ProductCategoryAssignmentSerializer,
        responses={
            200: success_response_schema(
                "ProductCategoryAssignmentResponse",
                ProductSerializer,
            ),
        },
    )
    @action(detail=True, methods=["put"], url_path="categories")
    def categories(self, request, slug=None):
        product = self.get_object()

        serializer = ProductCategoryAssignmentSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        product = ProductService.set_categories(
            product=product,
            category_ids=serializer.validated_data["category_ids"],
        )

        return success_response(
            data=ProductSerializer(product).data,
        )

    # -- Admin moderation -----------------------------------------------------

    @extend_schema(
        request=None,
        responses={
            200: success_response_schema(
                "ProductRemoveResponse",
                ProductSerializer,
            ),
        },
    )
    @action(detail=True, methods=["post"], url_path="remove")
    def remove_listing(self, request, slug=None):
        product = self.get_object()

        product = ProductLifecycleService.admin_remove(
            product=product,
        )

        return success_response(
            data=ProductSerializer(product).data,
        )


class _ProductOwnedImageMixin:
    """Shared ownership-resolution for product image sub-resource views."""

    permission_classes = [IsVerifiedVendor, IsOwnerVendor]

    def get_product(self, request, slug):
        product = get_object_or_404(
            Product.objects.alive().select_related(
                "store__vendor_profile",
            ),
            slug=slug,
        )

        self.check_object_permissions(request, product)

        return product


class ProductImageListCreateView(
    _ProductOwnedImageMixin,
    APIView,
):
    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    @extend_schema(
        responses={
            200: success_response_schema(
                "ProductImageListResponse",
                ProductImageSerializer,
            ),
        },
    )
    def get(self, request, slug):
        product = self.get_product(
            request,
            slug,
        )

        images = product.images.alive().order_by("display_order")

        return success_response(
            data=ProductImageSerializer(
                images,
                many=True,
            ).data,
        )

    @extend_schema(
        request=ProductImageUploadSerializer,
        responses={
            201: success_response_schema(
                "ProductImageCreateResponse",
                ProductImageSerializer,
            ),
        },
    )
    def post(self, request, slug):
        product = self.get_product(
            request,
            slug,
        )

        serializer = ProductImageUploadSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        image = ProductImageService.add_image(
            product=product,
            image=serializer.validated_data["image"],
            is_primary=serializer.validated_data.get("is_primary"),
            display_order=serializer.validated_data.get("display_order"),
        )

        return success_response(
            data=ProductImageSerializer(image).data,
            status=status.HTTP_201_CREATED,
        )


class ProductImageDetailView(
    _ProductOwnedImageMixin,
    APIView,
):
    @extend_schema(
        responses={204: None},
    )
    def delete(self, request, slug, image_id):
        product = self.get_product(
            request,
            slug,
        )

        image = get_object_or_404(
            product.images.alive(),
            pk=image_id,
        )

        ProductImageService.delete_image(
            product=product,
            image=image,
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )


class ProductImageSetPrimaryView(
    _ProductOwnedImageMixin,
    APIView,
):
    @extend_schema(
        request=None,
        responses={
            200: success_response_schema(
                "ProductImageSetPrimaryResponse",
                ProductImageSerializer,
            ),
        },
    )
    def patch(self, request, slug, image_id):
        product = self.get_product(
            request,
            slug,
        )

        image = get_object_or_404(
            product.images.alive(),
            pk=image_id,
        )

        image = ProductImageService.set_primary(
            product=product,
            image=image,
        )

        return success_response(
            data=ProductImageSerializer(image).data,
        )
