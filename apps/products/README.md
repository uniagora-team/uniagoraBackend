# Products App

The `products` app is the core marketplace listing domain of UniAGORA.

It owns product listings, product images, inventory, product lifecycle/expiry behavior, category assignments, and marketplace search composition.

The app follows the UniAGORA service-layer architecture: views handle HTTP concerns, serializers handle input/output validation, and services own business rules and transactional operations.

---

## Responsibilities

The products app owns:

* Product listings
* Product images
* Product inventory
* Product lifecycle and expiry
* Product category assignments
* Marketplace filtering
* PostgreSQL full-text keyword search
* Product view counting
* Product visibility rules

The products app does **not** own:

* Vendor identity or verification
* Store profile management
* Category creation or category-tree management
* Authentication
* User identity
* Chat
* Reviews
* Reports
* Notifications

The approved architecture defines `products` as responsible for products, images, inventory, lifecycle/expiry, and search composition.

---

## App Structure

```text
apps/products/
├── admin.py
├── apps.py
├── models.py
├── serializers.py
├── urls.py
├── views.py
├── services/
│   ├── __init__.py
│   ├── product_service.py
│   ├── inventory_service.py
│   ├── lifecycle_service.py
│   └── image_service.py
├── search/
│   ├── __init__.py
│   ├── filters.py
│   └── queries.py
└── tests/
    ├── __init__.py
    ├── factories.py
    ├── test_models.py
    ├── test_serializers.py
    ├── test_services.py
    └── test_views.py
```

---

## Domain Models

### Product

`Product` is the core marketplace listing.

A product:

* belongs to exactly one `Store`
* belongs to one `University`
* may belong to multiple categories
* may have up to eight images
* has exactly one primary image
* has an inventory quantity
* expires after 30 days
* has a lifecycle status
* maintains a view counter
* supports keyword search through PostgreSQL full-text search

The product's university is a deliberate denormalized copy of the store/vendor university used to make marketplace scoping efficient. It is set at creation and is not treated as an independent source of truth.

### ProductImage

`ProductImage` stores Cloudinary-backed product media.

Rules:

* Maximum of 8 images per product
* Exactly one primary image
* `display_order` controls image ordering
* Images are deleted when their product is deleted
* A partial unique database index provides a backstop against multiple primary images

The maximum-image rule and primary-image invariant are enforced by the service layer, with the database providing an additional primary-image uniqueness safeguard.

### ProductCategory

`ProductCategory` is the explicit many-to-many through table between products and categories.

Rules:

* A product may have multiple categories
* Duplicate product/category assignments are prevented
* Category deletion is protected
* Product deletion removes its category assignments

Category creation and hierarchy management remain the responsibility of the `categories` app.

---

## Product Conditions

Products support two conditions:

| Value  | Meaning                 |
| ------ | ----------------------- |
| `NEW`  | Unused product          |
| `USED` | Previously used product |

---

## Product Lifecycle

Product visibility is represented by `ProductStatus`.

| Status                 | Meaning                                     |
| ---------------------- | ------------------------------------------- |
| `ACTIVE`               | Visible, browsable, and searchable          |
| `EXPIRED`              | 30-day expiry reached; hidden but renewable |
| `HIDDEN_BY_SUSPENSION` | Hidden because the vendor was suspended     |
| `REMOVED_BY_ADMIN`     | Removed by Admin moderation                 |

Out-of-stock is **not** a lifecycle status.

Instead:

```text
quantity == 0
```

is represented as a derived availability condition. An `ACTIVE` product can therefore simultaneously be out of stock.

This separation prevents marketplace visibility and inventory state from being incorrectly coupled.

---

## Service Layer

Business logic is intentionally separated into specialized services.

### ProductService

Responsible for:

* Product creation
* Product updates
* Product deletion
* Store resolution
* Category assignment
* Product-level business rules

### InventoryService

Responsible for:

* Inventory quantity updates
* Inventory validation
* Stock-related business rules

### ProductLifecycleService

Responsible for:

* Product expiry
* Product renewal
* Admin removal
* Suspension-related hiding/reinstatement
* Lifecycle state transitions

Listing renewal is only valid from `EXPIRED`.

Renewal:

```text
EXPIRED
   │
   │ renew
   ▼
ACTIVE
```

Renewal resets `expires_at` to 30 days from the current time. Renewal is not permitted for products hidden by suspension or removed by Admin.

Expiry is applied by a scheduled sweep, not on request:

```bash
python manage.py sweep_expired_products        # manage.py entrypoint
python ops/cron.py sweep                       # standalone cron entrypoint
```

Both invoke the same runner (`ops/product_lifecycle.run_expiry_sweep`) and are idempotent, so they are safe to run on a frequent schedule. Deployment must wire one of them into a scheduler (cron/systemd timer/celery-beat) — without it, listings never transition to `EXPIRED`.

### ProductImageService

Responsible for:

* Adding images
* Deleting images
* Setting primary images
* Enforcing the maximum of eight images
* Maintaining primary-image invariants

The service layer is the authoritative location for these mutable business rules.

---

## Search

There is no standalone search app.

Search composition lives inside:

```text
apps/products/search/
├── filters.py
└── queries.py
```

### `filters.py`

Handles marketplace filtering such as:

* Category
* Price range
* Condition
* Ordering

### `queries.py`

Handles PostgreSQL full-text keyword search using the product search vector.

The architecture explicitly specifies this arrangement rather than introducing a separate search application.

---

## University Scoping

Marketplace product browsing is automatically scoped to the authenticated user's active university.

The `ActiveUniversityFilterBackend` provides this cross-cutting behavior.

Conceptually:

```text
Authenticated User
       │
       ▼
active_university
       │
       ▼
Product marketplace
       │
       ▼
Products belonging to that university
```

Users should not receive products from another university through the normal marketplace browse/search flow.

University scoping is applied automatically to product browse/search queries rather than being manually duplicated throughout product logic.

---

## Permissions

The products app reuses permission classes from `core.permissions`.

### Customer

Authenticated customers can:

* Browse products
* Retrieve visible products
* Search and filter products

### Verified Vendor

Verified vendors can:

* Create products
* View their own listings
* Update their own products
* Delete their own products
* Renew eligible listings
* Update inventory
* Manage categories
* Manage product images

### Admin

Admins can:

* Access moderation operations
* View products regardless of normal marketplace visibility
* Remove listings

Ownership is determined from the authenticated user's vendor/store relationship.

The API does not trust vendor or store ownership IDs supplied by clients. The architecture explicitly defines `IsOwnerVendor` as an object-level permission that resolves ownership from the authenticated user.

---

## API Operations

All API routes follow the project's `/api/v1/` versioning convention and standard response envelope.

### Product Listing

```text
GET /api/v1/products/
```

Provides marketplace browsing with:

* Active-university scoping
* Pagination
* Keyword search
* Category filtering
* Price filtering
* Condition filtering
* Ordering

### Product Detail

```text
GET /api/v1/products/{slug}/
```

Returns a product according to the product visibility rules.

A product view increments `views_count` for genuine customer interest only: views by the owning vendor and by admins are excluded, so the counter reflects external demand rather than self-activity.

### Create Product

```text
POST /api/v1/products/
```

Requires a verified vendor.

A new listing:

* belongs to the vendor's store
* inherits the vendor's university
* starts as `ACTIVE`
* requires a primary image
* receives its expiry date
* may receive category assignments

Client input cannot override server-controlled fields such as ownership, lifecycle state, expiry, or view count.

### Vendor's Products

```text
GET /api/v1/products/mine/
```

Returns products owned by the authenticated vendor.

### Update Product

```text
PUT/PATCH /api/v1/products/{slug}/
```

Only the owning verified vendor can update the listing.

### Delete Product

```text
DELETE /api/v1/products/{slug}/
```

Deletes the vendor's listing through `ProductService`.

### Renew Product

```text
POST /api/v1/products/{slug}/renew/
```

Renews an expired product.

Only:

```text
EXPIRED → ACTIVE
```

is permitted.

### Inventory

```text
PATCH /api/v1/products/{slug}/inventory/
```

Updates product quantity through `InventoryService`.

### Categories

```text
PUT /api/v1/products/{slug}/categories/
```

Replaces the product's category assignments through `ProductService`.

### Admin Removal

```text
POST /api/v1/products/{slug}/remove/
```

Admin-only moderation operation.

The product transitions to:

```text
REMOVED_BY_ADMIN
```

---

## Product Images

Product images are exposed as nested product resources.

### List Images

```text
GET /api/v1/products/{slug}/images/
```

### Upload Image

```text
POST /api/v1/products/{slug}/images/
```

Supports multipart uploads.

### Delete Image

```text
DELETE /api/v1/products/{slug}/images/{image_id}/
```

### Set Primary Image

```text
PATCH /api/v1/products/{slug}/images/{image_id}/primary/
```

Image operations are restricted to the owning verified vendor.

Cloudinary is the configured media-storage provider for product images. The architecture specifies one reusable Cloudinary-backed upload path across the platform rather than separate upload implementations per domain.

---

## Response Format

The products API follows the global UniAGORA response contract.

### Success

```json
{
  "success": true,
  "message": "",
  "data": {}
}
```

### Failure

```json
{
  "success": false,
  "message": "",
  "errors": {}
}
```

The response envelope is enforced globally and product views use the shared response helpers rather than introducing an app-specific response structure.

---

## Visibility Rules

Normal marketplace visibility requires:

```text
Product.status == ACTIVE
AND
Product.university == request.user.active_university
```

Special access is available to:

* The product owner
* Admin users

This allows vendors and admins to manage products that are not currently visible in the public marketplace.

Examples:

```text
ACTIVE
  └── visible to marketplace users in the same university

EXPIRED
  └── hidden
  └── renewable by owner

HIDDEN_BY_SUSPENSION
  └── hidden
  └── controlled by vendor suspension lifecycle

REMOVED_BY_ADMIN
  └── hidden
  └── controlled by admin moderation
```

---

## Database and Performance

The products domain is designed around the primary marketplace query patterns.

Important indexes include:

* `(university, status)` for marketplace browsing
* `status` for moderation/lifecycle queries
* `price` for price filtering and ordering
* `listed_at` for newest listings
* `expires_at` for expiry processing
* unique `slug` for detail-page lookup
* GIN index on `search_vector` for full-text search
* `(category_id, product_id)` on the product-category relationship

These indexes correspond to the approved database query strategy.

---

## Testing

The products app has comprehensive automated coverage across:

* Models
* Serializers
* Services
* Views
* Permissions
* Product lifecycle
* Inventory
* Image operations
* Category assignment
* Search/filter behavior
* University scoping
* Ownership rules
* Admin moderation
* Response envelopes



Cloudinary image tests mock the upload operation while still verifying the resulting Cloudinary-backed image properties, including:

```python
image.image.public_id
image.image.format
```

This avoids external Cloudinary API calls during automated tests while validating the application's media integration behavior.

---

## Architectural Rules

The products app follows these non-negotiable boundaries:

1. **Views remain thin.**
2. **Business logic belongs in services.**
3. **Serializers validate API input/output.**
4. **Permissions are reused from `core.permissions`.**
5. **Ownership is resolved server-side.**
6. **University scoping is automatic for marketplace browsing.**
7. **Product lifecycle transitions belong to `ProductLifecycleService`.**
8. **Inventory mutations belong to `InventoryService`.**
9. **Image invariants belong to `ProductImageService`.**
10. **Search composition belongs to `products/search/`.**
11. **Expected business exceptions use the shared exception system.**
12. **API responses follow the global response envelope.**
13. **Client input cannot control server-owned fields.**
14. **No product business rules are duplicated in views.**

---

## Dependencies

The products app depends on:

```text
common
stores
categories
universities
core
```

Conceptually:

```text
users
   │
   ▼
vendors
   │
   ▼
stores
   │
   ▼
products ───────► categories
   │
   └────────────► universities
```

The products app consumes vendor/store information but does not own vendor identity or storefront management.

---

## Out of Scope

The following are intentionally outside the products app:

* Cart
* Orders
* Payments
* Wallet
* Delivery
* Rider management
* Transactions as a standalone model
* Product recommendations
* AI search/recommendations

These concepts are outside the MVP scope defined by the approved product requirements.

---

## Definition of Done

The products app is considered complete when:

* Models are implemented according to the DDS
* Migrations apply successfully
* Product business rules are implemented in services
* Product endpoints are implemented
* Permissions are enforced
* University scoping is enforced
* Input validation is covered
* Lifecycle rules are covered
* Inventory rules are covered
* Image rules are covered
* Search/filter behavior is covered
* API response envelopes are consistent
* Automated tests pass
* Code passes project linting/formatting checks
* API documentation remains synchronized with endpoint behavior
