# Urja Meter Ops protocol record

## Evidence boundary

The assignment supplied the portal URL and credentials, but the redacted browser network evidence block was empty in this workspace. The committed fixtures are sanitized local examples and are not observations from the portal. No portal route, field, cookie, timestamp format, unit, count, or rate limit is presented as observed below unless explicitly labelled.

## Observed from the supplied brief

| Subject | Evidence status | Detail |
|---|---|---|
| Base URL | Supplied | `https://urja-ops.flockenergy.tech` |
| User-facing data | Supplied | Meter information, network placement, and recent consumption exist in the portal |
| Integration posture | Supplied | The portal must be treated as read-only |
| Credentials | Supplied | They are available to the operator but are not committed to this repository |

## Authentication record

| Item | Captured value |
|---|---|
| Login method | **UNVERIFIED** |
| Login path | **UNVERIFIED**; configured by `PORTAL_LOGIN_PATH` |
| Username field | **UNVERIFIED**; configured by `PORTAL_LOGIN_USERNAME_FIELD` |
| Password field | **UNVERIFIED**; configured by `PORTAL_LOGIN_PASSWORD_FIELD` |
| CSRF token | **UNVERIFIED** |
| Session cookie | **UNVERIFIED**; configured by `PORTAL_SESSION_COOKIE_NAME` or `PORTAL_LOGIN_SUCCESS_COOKIE` |
| Positive login signal | **UNVERIFIED**; configure a cookie or `PORTAL_LOGIN_SUCCESS_MARKER` |
| Login-page markers | **UNVERIFIED**; configure exact evidence markers through `PORTAL_LOGIN_PAGE_MARKERS` |
| Expiry response | **UNVERIFIED**; the adapter safely handles configured markers plus 401/403 |

The adapter requires an affirmative session signal after login. A status below 400 is not enough. When a safe read returns an evidence-configured login marker or 401/403, the adapter performs one single-flight login and retries the read. It checks the retried response again and raises `PortalSessionExpiredError` if it is still expired.

## Data endpoints and shapes

| Data | Path / method | Shape | Status |
|---|---|---|---|
| Meter list | **UNVERIFIED**; configured by `PORTAL_METER_LIST_PATH` | JSON list/wrapper or HTML table supported | **UNVERIFIED** |
| Meter detail | **UNVERIFIED**; configured by `PORTAL_METER_DETAIL_PATH` | JSON list/wrapper or HTML table supported | **UNVERIFIED** |
| Consumption | **UNVERIFIED**; configured by `PORTAL_CONSUMPTION_PATH` | JSON list/wrapper or HTML table supported | **UNVERIFIED** |
| Hierarchy | **UNVERIFIED**; configured by `PORTAL_HIERARCHY_PATH` | flat list, nested list, or wrapper keys `hierarchy`, `nodes`, `data`, `results` | Parser capability, not portal evidence |
| Pagination | **UNVERIFIED** | Public API pagination is independent of the portal | **UNVERIFIED** |
| Bulk/export path | **UNVERIFIED** | No bulk path is used | **UNVERIFIED** |

HTML table parsing does not depend on `<tbody>` or column position. It maps normalized header text, skips repeated header rows, and tolerates extra columns. A non-empty response that produces no known records raises schema drift rather than returning an empty success.

## Normalization and quality

- Timestamp strings retain their original value. Invalid or missing timestamps remain `null`.
- Naive timestamps use the configured `PORTAL_TIMEZONE` and receive `assumed_timezone`; slash dates require `PORTAL_DATE_FORMAT` to avoid a silent day/month guess.
- Numeric parsing supports explicit `en_US`, `de_DE`, `fr_FR`, or conservative auto handling. Ambiguous separators are flagged rather than guessed.
- Units are never defaulted. Documented `Wh` to `kWh` and `MWh` to `kWh` conversions receive `unit_converted`; unknown or missing units are flagged.
- Meter and reading duplicates remain as separate records with `duplicate` flags.
- Readings can receive `missing`, `invalid`, `out_of_order`, `negative_value`, `unknown_unit`, `ambiguous_number`, and `assumed_timezone` flags.
- Hierarchy reconstruction preserves duplicate records, marks orphans and cycles, computes meter and consumption rollups, and adds `Unassigned` for meters without an observed node.

## Request-rate guidance

The portal's actual rate limit is **UNVERIFIED**. The live adapter therefore uses a small configurable concurrency cap, bounded retries with jitter only for transient errors, and a circuit breaker. Keep `PORTAL_MAX_CONCURRENCY` conservative and use the local index for repeated reads. The public API has a bounded, single-process rate limiter; a multi-instance deployment needs a shared limiter.

## Configuration checklist for a live capture

Record the redacted method, path, request fields, content type, response shape, cookie attributes, expiry response, pagination, units, timezone, date format, and any bulk path. Set the matching `.env` values only after capture. Never commit credentials, cookies, bearer values, or unredacted personal payloads.
