# Aadi Street Festival API endpoints - Shareable guide

This standalone guide can be shared with developers integrating with the Aadi Street Festival API. It lists every HTTP endpoint currently defined by the Azure Function source.

## Base URLs

Festival API base:

```text
https://aadi-street-festival-api-2026.azurewebsites.net/api/festival
```

Root API base, used by the Google exchange, health, master-list, and retired routes:

```text
https://aadi-street-festival-api-2026.azurewebsites.net/api
```

Never place a Cosmos DB key, Azure connection string, Google client secret, or real API key in this document or in a public repository.

## Authentication types

| Name | Request authentication | Used for |
|---|---|---|
| Public browser origin | No credential; request must come from an allowed origin | Parent session creation and published stall catalogue |
| Parent session | `Authorization: Bearer <parent-session-token>` | Parent payment submission, status lookup, student details, and wallet-session creation |
| Wallet session | `Authorization: Bearer <wallet-session-token>` | Reading one matched Parent wallet |
| Google user | `Authorization: Bearer <Google-ID-token>` | Students, stall workers, and administrators |
| Classmate stall key | `X-Aadi-Api-Key: <private-key>` | Key status and deductions for explicitly allowed stalls only |
| Signed service | HMAC service headers documented separately | Backend-to-backend synchronisation |

## Stall endpoints

These are the endpoints for the classmate's stall application.

### Check the stall API key

```http
GET https://aadi-street-festival-api-2026.azurewebsites.net/api/festival/api-key/status
X-Aadi-Api-Key: <PRIVATE_API_KEY>
```

A successful response confirms the application name, permissions, and allowed stall IDs without changing any wallet.

### Deduct money at a stall

```http
POST https://aadi-street-festival-api-2026.azurewebsites.net/api/festival/stalls/STALL-07/deductions
Content-Type: application/json
X-Aadi-Api-Key: <PRIVATE_API_KEY>
```

```json
{
  "tokenNumber": "123",
  "amount": 10,
  "idempotencyKey": "stall07-sale-unique-0001"
}
```

The stall ID is part of the URL. The API key must be authorised for that exact stall. The operation is atomic and idempotent. The response does not reveal the remaining wallet balance, Parent information, UTR, or payment history.

### Reverse a stall deduction

```http
POST /stalls/{stallId}/deductions/{transactionId}/reverse
Authorization: Bearer <Google-ID-token>
Content-Type: application/json
```

```json
{
  "reason": "Approved correction reason",
  "idempotencyKey": "reversal-unique-operation-id"
}
```

Only an authorised administrator with `tokens:reverse` permission can reverse a deduction. The classmate API key cannot reverse transactions.

## Complete festival endpoint list

All paths in this table are relative to the festival API base.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/session` | Allowed public browser origin | Issues a short-lived Parent session token |
| `GET` | `/catalogue` | Allowed public browser origin | Returns published stall names, categories, offerings, and published locations |
| `GET` | `/catalogue/admin` | Admin or `catalogue:manage` | Returns published and draft catalogue records |
| `POST` | `/catalogue/preview` | Admin or `catalogue:manage` | Validates and previews catalogue CSV text without saving it |
| `POST` | `/catalogue/import` | Admin or `catalogue:manage` | Imports reviewed stall catalogue records |
| `POST` | `/catalogue/update` | Admin or `catalogue:manage` | Updates one stall catalogue record |
| `POST` | `/catalogue/location` | Admin or `catalogue:manage` | Updates a stall's floor, zone, landmark, and publication status |
| `POST` | `/catalogue/publish` | Admin or `catalogue:manage` | Publishes or unpublishes catalogue records |
| `GET` | `/auth/me` | Google user | Returns the verified email, resolved role, and assigned stall IDs |
| `GET` | `/check-ins?reference=` | Super Admin, Teacher Admin, or Council Lead | Looks up an entrance record using a tracking code or three-digit card/token number |
| `POST` | `/check-ins` | Super Admin, Teacher Admin, or Council Lead | Records one approved entrance check-in |
| `GET` | `/api-key/status` | Classmate stall key | Confirms the API key, `tokens:deduct` permission, and allowed stalls |
| `GET` | `/accounts?couponNumber=&studentName=&grade=` | `accounts:lookup` | Finds a minimal account reference |
| `POST` | `/accounts` | `accounts:write` or authorised Admin | Creates an account and zero-balance wallet; disposable test creation is Super Admin only |
| `GET` | `/payments?trackingCode=` | Parent session or `payments:status` | Returns the safe status of one payment request |
| `GET` | `/payments?utrId=` | Admin or `payments:private` | Returns private payment details for an administrator |
| `GET` | `/payments?list=1&limit=` | `payments:list` | Returns the administrator payment queue |
| `POST` | `/payments` | Parent session or `payments:parent-submit` | Submits a Parent payment request; retained as an active alias |
| `POST` | `/payments/parent` | Parent session or `payments:parent-submit` | Submits a Pending Parent payment request |
| `POST` | `/payments/school-entry` | Admin or `payments:direct` | Creates an immediately approved school payment and credits the wallet |
| `POST` | `/payments/approve` | Admin or `payments:approve` | Approves a Pending payment and credits it exactly once |
| `POST` | `/payments/verify` | Admin or `payments:approve` | Records/verifies the payment verification step |
| `POST` | `/payments/reject` | Admin or `payments:reject` | Rejects a Pending payment with a reason |
| `POST` | `/payments/correct` | Admin or `payments:correct` | Applies an audited payment reversal or adjustment |
| `POST` | `/parents/wallet-session` | Parent session | Matches card/token number and mobile number, then issues a wallet-specific token |
| `POST` | `/parents/student-details` | Parent session | Returns saved student name and grade after an exact card/token and mobile match |
| `GET` | `/parents/wallet` | Wallet session | Returns one Parent wallet's balance, pending amount, status, and recent stall purchases |
| `GET` | `/coupons?couponNumber=` | `coupons:read` | Returns a wallet/coupon status and balance to authorised users only |
| `POST` | `/coupons/correct` | `coupons:correct` | Applies an audited refund or balance correction |
| `POST` | `/tokens/reverse` | Authorised Admin with `tokens:reverse` | Legacy active Admin reversal operation using a JSON-supplied transaction reference |
| `GET` | `/transactions?couponNumber=&limit=` | `transactions:read` | Returns authorised wallet transaction history |
| `GET` | `/assignments?email=` | Self, school Admin, or `assignments:read` | Returns stall assignments visible to the caller |
| `GET` | `/reconciliation` | `reconciliation:read` | Returns aggregate reconciliation totals |
| `GET` | `/audit?limit=` | `audit:read` | Returns authorised audit records |
| `GET` | `/stall-collections?stallId=` | Assigned stall, Admin, or `collections:read` | Returns collections restricted to the caller's authorised stalls |
| `POST` | `/stall-collections` | Assigned stall, Admin, or `collections:write` | Records a stall collection |
| `POST` | `/stalls/{stallId}/deductions` | Assigned Google stall worker or exact stall-scoped classmate key | Atomically deducts an amount from a three-digit card/token wallet |
| `POST` | `/stalls/{stallId}/deductions/{transactionId}/reverse` | Authorised Admin with `tokens:reverse` | Reverses one exact stall deduction with an audit record |
| `POST` | `/sync/records` | Signed service with `sync:write` | Creates or updates an idempotent external record |
| `POST` | `/sync/change-requests` | Signed service with `sync:request` | Requests an administrator-reviewed protected-field change |
| `GET` | `/sync/changes?since=&limit=` | Signed service with `sync:read` | Reads safe source-scoped changes after a checkpoint |
| `GET` | `/sync/status?idempotencyKey=` | Signed service with `sync:read` | Reads the status of one source-scoped sync operation |
| `GET` | `/sync/status?recordType=&externalRecordId=` | Signed service with `sync:read` | Finds a source-scoped external record link |
| `POST` | `/sync/retry` | Signed service with `sync:retry` | Retries the exact original idempotent sync envelope |

## Root API endpoints

These paths are relative to the root API base, not the festival base.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/auth/google` | Google credential in JSON | Verifies a Google credential and returns the user's festival role and assignments |
| `GET` | `/health` | Google Admin | Reports whether the API and Cosmos DB configuration are reachable |
| `GET` | `/master-lists` | Super Admin, Teacher Admin, or `administrator` | Returns the latest master-list imports |
| `POST` | `/master-lists` | Super Admin, Teacher Admin, or `administrator` | Imports up to 500 student, teacher, council, stall, or role rows |

## Retired endpoints

These routes still exist only to return HTTP `410 endpoint_retired`. New applications must not use them.

| Method | Path | Replacement |
|---|---|---|
| `GET`, `POST` | `/coupons` | `/api/festival/coupons` |
| `GET`, `POST` | `/stall-collections` | `/api/festival/stall-collections` |
| `GET`, `POST`, `PATCH` | `/topups` | `/api/festival/payments` |

The obsolete `/api/festival/tokens/deduct` and `/api/festival/coupons/deduct` routes do not exist and return `404 endpoint_not_found`.

## Common status codes

| Status | Meaning |
|---|---|
| `200` | Successful read, update, duplicate-safe retry, or deduction |
| `201` | New record or session created |
| `202` | Change request accepted for later review |
| `204` | Successful CORS preflight |
| `304` | Parent wallet has not changed since the supplied ETag |
| `400` | Invalid JSON, fields, identifiers, or values |
| `401` | Authentication is missing, expired, or incorrect |
| `403` | Authentication worked, but the caller lacks permission or stall scope |
| `404` | Record or endpoint not found |
| `409` | Duplicate/conflicting request, insufficient balance, or invalid state transition |
| `410` | Retired endpoint |
| `413` | Master-list upload is too large |
| `429` | Rate limit exceeded |
| `500`/`503` | Backend or data-store failure |

## CORS

Browser clients must run from an origin allowed by the API. Supported API routes answer `OPTIONS` preflight requests where required. A command-line program or server-to-server request does not rely on browser CORS.

## Source references

The route definitions are implemented in:

- `api/src/functions/festivalApi.js`
- `api/src/functions/authGoogle.js`
- `api/src/functions/health.js`
- `api/src/functions/masterLists.js`
- `api/src/functions/coupons.js`
- `api/src/functions/stallCollections.js`
- `api/src/functions/topups.js`
