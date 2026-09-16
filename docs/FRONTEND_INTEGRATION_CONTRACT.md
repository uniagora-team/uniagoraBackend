# Frontend Integration Contract

**Audience:** the UniAGORA frontend engineer(s).
**Purpose:** everything about the API's behavior that is easy to get wrong,
learned the hard way on the backend. Read this before wiring up auth, uploads,
and listing flows. Anything not covered here follows the OpenAPI schema at
`/api/schema/` (Swagger UI at `/api/docs/`).

---

## 1. CORS — how the browser is allowed to call us

The API enforces an origin allowlist. Local dev allows any origin
(`CORS_ALLOW_ALL_ORIGINS=True` in `config/settings/development.py`), but any
other deployment must set, in env:

```bash
CORS_ALLOWED_ORIGINS=https://app.uniagora.app,https://staging.uniagora.app
# optional regex alternative:
# CORS_ALLOWED_ORIGIN_REGEXES=https://.*\.uniagora\.app
```

If the browser reports a CORS error on every call, this setting is missing —
it is env config, not code. The API is JWT-in-`Authorization`-header based;
no cookies are required for normal flows.

---

## 2. JWT lifecycle — the refresh race you must handle

The API issues **30-minute access tokens** and rotates refresh tokens
(`ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`): every refresh
call **invalidates the refresh token that was used** and returns a new pair.

Consequence: if two tabs fire a refresh at the same moment, one succeeds and
the other's token is now blacklisted → a random logout. The **frontend must
serialize refresh calls**:

* Keep exactly one refresh-in-flight at a time (a shared promise/mutex in the
  API client).
* All 401-handling code must await that shared promise, then retry the
  original request with the new access token.
* If refresh itself fails with 401, log the user out and route to login —
  do not loop.

Recommended skeleton (axios-style pseudocode):

```js
let refreshPromise = null;

api.interceptors.response.use(null, async (error) => {
  if (error.response?.status !== 401) throw error;
  refreshPromise ??= refreshTokens().finally(() => { refreshPromise = null; });
  await refreshPromise;          // one network round-trip, N waiters
  return api(error.config);      // retry once with the new access token
});
```

---

## 3. Response envelope — unwrap before use

Every JSON response is wrapped:

```json
// success
{ "success": true, "message": "", "data": { ... } }

// error
{ "success": false, "message": "", "errors": { ... } }
```

Read payloads from `data`, error details from `errors` (a field-keyed object
when validation failed). Do not branch on HTTP status alone; `success` is the
authoritative flag.

---

## 4. Pagination shape

List endpoints return:

```json
{
  "success": true,
  "message": "",
  "data": {
    "count": 128,
    "total_pages": 7,
    "current_page": 1,
    "page_size": 20,
    "next": "http://…?page=2",
    "previous": null,
    "results": [ ... ]
  }
}
```

Page size defaults to 20, max 100, via `?page_size=`. `next`/`previous` are
absolute URLs or `null`.

---

## 5. Uploads — product creation is multipart

`POST /api/v1/products/` requires a **primary image file**, so the request is
`multipart/form-data` (the OpenAPI request schema documents `format: binary`
for these fields — don't send JSON with URL strings; file fields accept files
only):

* `name`, `price`, `condition`, `quantity`, optional `campus_location`,
  `description`, `category_ids` (repeatable), and **`primary_image` (file)**.
* Send with `FormData`; do not set `Content-Type` manually — let the client
  set the multipart boundary.

Other upload endpoints (logo changes, vendor documents, chat attachments)
likewise take files, not URL strings. Server-enforced limits: images must be
valid image types, documents valid document types; the deploy's reverse proxy
must allow bodies of at least the API's upload policy (8 MB) or uploads fail
with 413 before reaching Django.

Every image URL returned by the API is **absolute**
(`https://res.cloudinary.com/...`) — render directly, no prefixing.

---

## 6. Product detail & `views_count`

`GET /api/v1/products/{slug}/` is the canonical detail lookup (by slug, not
id). Views by the listing's owner and by admins **do not** increment
`views_count` — the counter reflects genuine customer interest, so the vendor
dashboard can present it as such.

---

## 7. Listing lifecycle (what the vendor UI must surface)

* Listings expire automatically 30 days after listing/renewal — but only when
  the backend's scheduled sweep runs (ops-managed; deployment wires cron).
  Between `expires_at` passing and the sweep running, a listing can still read
  `ACTIVE` — treat `expires_at` as the display source of truth for
  "expires in X".
* `EXPIRED` → vendor may renew → back to `ACTIVE` with a fresh 30-day window.
* Suspended vendors' listings go `HIDDEN_BY_SUSPENSION` and return on
  reinstatement (unless expired while hidden).
* Deleting a listing is a **soft delete** from the vendor's perspective; the
  API generally surfaces it as gone.

---

## 8. Duplicate matric numbers after soft delete

A vendor application that was soft-deleted releases its matric number: the
uniqueness rule applies to live applications only. If the UI pre-validates
"matric number already taken" client-side, re-check server-side on submit —
the server's answer is authoritative and changes over time.

---

## 9. Docs URLs

* OpenAPI schema: `GET /api/schema/`
* Swagger UI: `/api/docs/`
* ReDoc: `/api/redoc/`
