# `common` — Shared Infrastructure

`common` owns **zero domain models and zero API endpoints**. It exists so
every other app in the eleven-app build order can inherit one, single
implementation of persistence, response-shaping, pagination, media-upload,
and error-handling conventions instead of reimplementing them per app.

This document is the usage reference for the components in this app, for
engineers building `universities`, `users`, `vendors`, `stores`,
`categories`, `products`, `chat`, `reviews`, `reports`, and `notifications`.

## Required project wiring

Add to `config/settings/base.py`:

```python
INSTALLED_APPS = [
    ...,
    "apps.common",
    "apps.core",
    ...,
]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["apps.common.renderers.EnvelopeJSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
}
```

Dependencies this app assumes are installed: `django`, `djangorestframework`,
`cloudinary`, `django-cloudinary-storage`.

## `models.BaseModel`

Every model in every other app inherits this instead of `models.Model`:

```python
from apps.common.models import BaseModel

class University(BaseModel):
    name = models.CharField(max_length=150, unique=True)
    ...
```

Supplies `id` (UUID), `created_at`, `updated_at`, `is_deleted`, and one
manager:

- `Model.objects` — **unfiltered by default.** `Model.objects.all()`
  returns every row, including soft-deleted ones.
- `Model.objects.alive()` — explicitly excludes soft-deleted rows. Use
  this in customer-facing browse/detail queries and anywhere a
  soft-deleted row must not appear.
- `Model.objects.dead()` — only soft-deleted rows (admin "recently
  removed" views, audits).

This is a deliberate, revised design (see CTO review discussion): the
default manager does **not** silently filter, so aggregations, analytics,
reporting, and admin queries all see the true row count unless a query
explicitly opts into `.alive()`. Domain apps' own custom managers (e.g.
`Product.objects.visible()` per Backend Architecture §6) are expected to
call `.alive()` internally alongside their own status/university scoping.

Deleting an instance soft-deletes by default (`obj.delete()`). Pass
`obj.delete(hard=True)` only for the specific hard-delete paths documented
per-relationship in DDS §8 (e.g. `ProductImage`, `VendorDocument`,
`MessageAttachment` — genuinely dependent child rows). The queryset-level
equivalents are `.delete()` (bulk soft-delete) and `.hard_delete()`.

## `mixins.AutoSlugMixin`

For any model with a DDS-specified auto-derived slug (`University`,
`Store`, `Category`, `Product`):

```python
class Store(AutoSlugMixin, BaseModel):
    display_name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    slug_source_field = "display_name"
```

The slug is generated on first save only, from `slug_source_field`, and
deduplicated with a numeric suffix on collision.

## `response.success_response` / `error_response`

Use directly in any view that isn't a `ListAPIView`/paginated response
(which already get the envelope from `pagination.py`):

```python
from apps.common.response import success_response

def post(self, request):
    vendor = VendorApplicationService.apply(request.user, ...)
    return success_response(data=VendorProfileSerializer(vendor).data,
                             message="Application submitted.", status=201)
```

Views generally don't need `error_response` directly — raise an
`ApplicationError` subclass from the service layer instead, and the global
exception handler builds the envelope.

## `exceptions.ApplicationError`

Domain apps subclass this for business-rule failures raised from services:

```python
from apps.common.exceptions import ConflictError

class VendorSuspensionService:
    @staticmethod
    def reinstate(vendor_profile):
        if vendor_profile.status != VendorStatus.SUSPENDED:
            raise ConflictError("Vendor is not currently suspended.")
        ...
```

Available base classes: `ApplicationError` (400), `NotFoundError` (404),
`PermissionDeniedError` (403), `ConflictError` (409). Views never need a
`try/except` for these — `custom_exception_handler` (wired as
`EXCEPTION_HANDLER`) catches them globally.

## `pagination.StandardResultsSetPagination`

Wired globally via `DEFAULT_PAGINATION_CLASS`; no per-view configuration
needed unless a view legitimately needs a different `page_size`.

## `fields.CloudinaryImageField` / `CloudinaryDocumentField`

```python
from apps.common.fields import CloudinaryImageField, validate_upload_size, validate_image_content_type

class ProductImage(BaseModel):
    image = CloudinaryImageField(folder="uniagora/products", validators=[validate_upload_size, validate_image_content_type])
```

## `serializers.CloudinaryFileField`

DRF-side counterpart to the Cloudinary model fields above. Registered
globally at startup (`CommonConfig.ready()`), so every `ModelSerializer`
renders Cloudinary-backed fields (`product images`, `vendor documents`,
`business/university logos`, future chat attachments) as absolute
`https://res.cloudinary.com/...` URLs — no per-serializer workaround.

```python
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "is_primary", "display_order"]
    # `image` needs NO explicit field — the global mapping emits the URL.
```

Write serializers that accept uploads should declare the field explicitly
(uploads only — clients can never submit URL strings):

```python
from apps.common.serializers import CloudinaryFileField

class UniversityAdminWriteSerializer(serializers.ModelSerializer):
    logo = CloudinaryFileField(required=False, allow_null=True)
```

## `validators.validate_phone_number`

```python
from apps.common.validators import validate_phone_number

class VendorProfileSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(validators=[validate_phone_number])
```


Domain serializers do **not** need a shared base class for `id`/
`created_at`/`updated_at`. DRF's `ModelSerializer` already infers
`read_only=True` for any model field with `editable=False` (`BaseModel.id`)
or `auto_now`/`auto_now_add=True` (`created_at`, `updated_at`) —
see `rest_framework.utils.field_mapping.get_field_kwargs`. Simply list
them in `Meta.fields`:

```python
class UniversitySerializer(serializers.ModelSerializer):
    class Meta:
        model = University
        fields = ["id", "created_at", "updated_at", "name", "short_name", "slug", "logo", "is_active"]
```

No shared code is required — an earlier version of this app included a
`BaseModelSerializer` for this, which was removed as an unnecessary
abstraction over a problem DRF already solves.

## `admin.SoftDeleteAdminMixin`

```python
@admin.register(Product)
class ProductAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (*SoftDeleteAdminMixin.list_display, "name", "status")
```

The DDS documents exactly one model needing a truncated `__str__`
(`Message.__str__`, §4.11 — "truncates body to 50 chars"). A shared
utility with a single confirmed consumer is premature abstraction; the
three-line truncation now lives directly in `chat/models.py` when that
app is built, rather than in `common`.

## What is deliberately **not** in this app

- **Permissions** (`IsVerifiedVendor`, `IsOwnerVendor`, etc.) — these are
  domain-aware and belong to `core/permissions.py` per the Backend
  Architecture's app-boundary table (§2). `common` has zero domain
  knowledge, so it cannot express "verified vendor" or "owner" checks.
- **Enums** (`VendorStatus`, `ProductStatus`, etc.) — every enum in DDS §5
  is scoped to the model that owns it. Defining them here would let
  `common` "know" about vendor/product domain concepts, violating its
  stated boundary.
- **A `filters.py`** — `ActiveUniversityFilterBackend` is domain-aware
  (needs `User.active_university`) and belongs to `core`, not `common`.
