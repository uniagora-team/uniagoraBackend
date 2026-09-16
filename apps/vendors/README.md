# Vendors App

The `vendors` app manages vendor onboarding, vendor profiles, verification status, vendor documents, and administrative vendor lifecycle actions within UniAGORA.

It is responsible for the **vendor identity and verification domain**. Storefront management and product management belong to subsequent apps.

## Responsibilities

The app handles:

* Vendor profile creation and ownership.
* Student and business vendor applications.
* Student verification documents.
* Vendor verification status.
* Automatic vendor approval in the MVP.
* Vendor suspension and reinstatement.
* Vendor profile retrieval.
* Administrative vendor management.
* Vendor-specific business validation and database constraints.

## Architecture

The app follows the project's service-layer architecture:

```text
HTTP Request
    │
    ▼
Views / ViewSet
    │
    ▼
Serializers
    │
    ▼
Services
    │
    ▼
Models / Database
```

Business operations are kept in services rather than views or serializers.

### Services

| Service                     | Responsibility                                             |
| --------------------------- | ---------------------------------------------------------- |
| `VendorApplicationService`  | Creates vendor applications and performs MVP auto-approval |
| `VendorVerificationService` | Handles vendor approval/rejection state transitions        |
| `VendorSuspensionService`   | Handles vendor suspension/reinstatement                    |
| `VendorDocumentService`     | Creates and approves vendor documents                      |

## Models

### `VendorProfile`

Represents the vendor relationship between a user and a university.

Important fields include:

* `user`
* `university`
* `vendor_type`
* `store_name`
* `phone_number`
* `matric_number`
* `department`
* `level`
* `business_name`
* `business_address`
* `business_logo`
* `status`
* `reviewed_by`
* `reviewed_at`

A user can own only one vendor profile.

### `VendorDocument`

Represents a document submitted by a student vendor as proof of studentship.

Important fields include:

* `vendor_profile`
* `document_type`
* `file`
* `status`
* `uploaded_at`
* `reviewed_at`

The MVP currently supports one submitted document per vendor through service-layer enforcement.

## Vendor Types

The app supports two vendor types.

### Student Vendor

Student vendors require:

* Store name
* Phone number
* University
* Matric number
* Department
* Level
* Proof-of-studentship document

### Business Vendor

Business vendors require:

* Store name
* Phone number
* University
* Business name
* Business address

A business vendor does not require a verification document in the MVP. A business logo is optional.

## Verification Flow

Vendor applications are automatically approved in the MVP.

For a student vendor:

```text
Application
    │
    ├── Create VendorProfile
    │
    ├── Create VendorDocument
    │
    ├── Approve Document
    │
    └── Verify VendorProfile
```

The complete operation runs inside a database transaction.

The resulting states are:

```text
VendorProfile → VERIFIED
VendorDocument → APPROVED
```

Manual rejection functionality exists at the service layer for future use but is not exposed through the current MVP API because applications are automatically approved.

## Vendor Status

The vendor lifecycle supports:

```text
PENDING
   │
   └── VERIFIED
          │
          └── SUSPENDED
                 │
                 └── VERIFIED
```

`REJECTED` is retained for future manual-review workflows.

Invalid state transitions raise the project's `ConflictError` and are returned as HTTP `409 Conflict` responses.

## Database Constraints

The database provides important integrity guarantees in addition to serializer and service validation.

### One Vendor Per User

`VendorProfile.user` is a `OneToOneField`, ensuring that an account cannot own multiple vendor profiles.

### Matric Number Uniqueness

Student matric numbers are unique within a university:

```text
(university, matric_number)
```

The uniqueness constraint applies only when `matric_number` is present, allowing business vendors to have a null matric number. The constraint is also scoped to live (non-soft-deleted) rows, so a matric number freed by a soft-deleted application can be reused.

### Conditional Vendor Fields

Database-level validation prevents invalid vendor records such as:

* Student vendors without required student information.
* Business vendors without required business information.

Serializer validation provides friendlier API-level errors before the database constraint is reached.

## API

Base route:

```text
/api/v1/vendors/
```

### Customer Endpoints

#### Apply as Vendor

```http
POST /api/v1/vendors/
```

Creates a vendor application for the authenticated customer.

The request determines whether the application is for a student or business vendor.

#### Get My Vendor Profile

```http
GET /api/v1/vendors/me/
```

Returns the authenticated user's vendor profile.

A user without a vendor profile receives `404 Not Found`.

### Admin Endpoints

#### List Vendors

```http
GET /api/v1/vendors/
```

Returns vendor profiles for authorized administrators.

#### Retrieve Vendor

```http
GET /api/v1/vendors/{id}/
```

Returns a specific vendor profile.

#### Suspend Vendor

```http
POST /api/v1/vendors/{id}/suspend/
```

Suspends a verified vendor.

#### Reinstate Vendor

```http
POST /api/v1/vendors/{id}/reinstate/
```

Reinstates a suspended vendor.

There is intentionally no vendor deletion endpoint in the MVP.

## Permissions

The API separates customer and administrative capabilities.

| Operation        | Customer | Admin |
| ---------------- | -------: | ----: |
| Apply as vendor  |        ✅ |     — |
| View own profile |        ✅ |     — |
| List vendors     |        ❌ |     ✅ |
| Retrieve vendors |        ❌ |     ✅ |
| Suspend vendor   |        ❌ |     ✅ |
| Reinstate vendor |        ❌ |     ✅ |

Authentication and role-based permissions are provided by the project's `core` and `users` infrastructure.

## Media Storage

Vendor documents and business logos use the project's configured Cloudinary-backed media storage.

Tests isolate the Cloudinary upload boundary so the test suite does not require live Cloudinary credentials or network access.

## Validation

`VendorApplicationSerializer` is the write serializer for vendor applications.

It performs conditional validation based on `vendor_type`.

It also performs a friendly duplicate matric-number check and returns the error against `matric_number`.

The database constraint remains the final integrity backstop.

The read-only `VendorProfileSerializer` is used to represent vendor profiles and their associated documents.

## Testing

The app has dedicated tests covering:

* Vendor model behavior.
* Database constraints.
* Vendor application services.
* Verification transitions.
* Suspension and reinstatement.
* Serializer validation.
* Duplicate matric numbers.
* Customer API behavior.
* Administrative API behavior.
* Authentication and permissions.
* Student document submission.

## Migrations

Migrations are generated from the Django models using the project's Django environment.

After modifying vendor models:

```bash
python manage.py makemigrations vendors
```

Verify migration consistency:

```bash
python manage.py makemigrations --check
```

Apply migrations:

```bash
python manage.py migrate
```

## Dependencies

The vendors app depends on:

* `apps.common`
* `apps.core`
* `apps.users`
* `apps.universities`

The app depends on `stores` and `products` for the suspension cascade:
when a vendor is suspended, their storefront is deactivated and their
product listings are hidden through `StoreService` and
`ProductLifecycleService`. Reinstate reverses both.

### Suspension Cascade

`VendorSuspensionService` coordinates the vendor lifecycle across
boundaries in a single transaction, per the approved backend design:
