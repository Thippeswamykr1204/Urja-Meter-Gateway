# Urja Meter Ops capture worksheet

This worksheet records the exact browser observation needed for each setting. It does not assume a portal route, field name, response shape, timestamp format, unit, or request limit.

## Browser setup

1. Open `https://urja-ops.flockenergy.tech`.
2. Open DevTools with `F12` or `Cmd+Option+I`.
3. Select **Network**.
4. Enable **Preserve log** and **Disable cache**.
5. Include **Document** and **Fetch/XHR** requests.
6. Perform one normal login and ordinary read-only navigation.
7. Use **Copy → Copy as cURL** for requests that matter, then remove passwords, cookies, authorization values, CSRF values, session identifiers, and personal data.

## Capture record

| Setting | Exact observation that fills it | DevTools action | Status / value |
|---|---|---|---|
| `APP_ENV` | Local deployment environment name | Confirm the intended local/test/production invocation; no portal request fills this | `local` |
| `DEMO_MODE` | Whether the process uses fixtures or the portal | Confirm the intended run mode before starting the API | `true` until live settings are verified |
| `API_HOST` | Local bind address | Inspect the API startup command or local browser URL | `127.0.0.1` unless changed locally |
| `API_PORT` | Local API port | Inspect the API startup command or local browser URL | `8000` unless changed locally |
| `API_READ_KEY` | Local read credential | Generate a local secret; never obtain this from the portal | Set locally; never commit |
| `API_ADMIN_KEY` | Local admin credential | Generate a separate local secret; never obtain this from the portal | Set locally; never commit |
| `API_READ_KEYS` | Additional local read credentials | Confirm local deployment configuration | Empty unless needed |
| `API_ADMIN_KEYS` | Additional local admin credentials | Confirm local deployment configuration | Empty unless needed |
| `API_PROXY_TARGET` | API origin used by the Vite development proxy | Confirm the API address used by the web console | `http://127.0.0.1:8000` unless changed locally |
| `DATABASE_URL` | Local SQLite file location | Confirm the local run command and backup location | `sqlite:///./flock_energy.db` unless changed locally |
| `PORTAL_BASE_URL` | Final portal origin after redirects | Inspect the full request URL and redirect chain for login and one read | `UNVERIFIED` until captured |
| `PORTAL_USERNAME` | Operator credential identifier | Do not paste the value; keep it in the private local environment | Private local value |
| `PORTAL_PASSWORD` | Operator credential | Do not paste the value; keep it in the private local environment | Private local value |
| `PORTAL_LOGIN_PATH` | Login request method and exact path | Submit login and copy the login request URL without credentials or cookies | `UNVERIFIED` |
| `PORTAL_METER_LIST_PATH` | Exact meter-list request path | Open the meter list and inspect the request that returns its records | `UNVERIFIED` |
| `PORTAL_METER_DETAIL_PATH` | Exact detail path and identifier placement | Open one meter from the list and inspect the detail request | `UNVERIFIED` |
| `PORTAL_CONSUMPTION_PATH` | Exact consumption path and identifier placement | Open consumption for one meter and inspect the request | `UNVERIFIED` |
| `PORTAL_HIERARCHY_PATH` | Exact hierarchy request path | Open the hierarchy view and inspect its request | `UNVERIFIED` |
| `PORTAL_LOGIN_USERNAME_FIELD` | Form or JSON key containing the username | Inspect the login request payload after removing the value | `UNVERIFIED` |
| `PORTAL_LOGIN_PASSWORD_FIELD` | Form or JSON key containing the password | Inspect the login request payload after removing the value | `UNVERIFIED` |
| `PORTAL_SESSION_COOKIE_NAME` | Session cookie name and safe attributes | Inspect `Set-Cookie` on the successful login response | `UNVERIFIED` |
| `PORTAL_LOGIN_SUCCESS_COOKIE` | Cookie that proves successful login, if distinct from the session cookie | Compare cookies before and after login | `UNVERIFIED` |
| `PORTAL_LOGIN_SUCCESS_MARKER` | Stable body or final-URL marker after login | Inspect the successful login response and redirect target | `UNVERIFIED` |
| `PORTAL_LOGIN_PAGE_MARKERS` | Stable body or URL markers returned after expiry | Wait for natural expiry or delete only your own session cookie, then reload a read-only page | `UNVERIFIED` |
| `PORTAL_TIMEZONE` | Explicit timezone or reliable interpretation of raw timestamps | Compare the raw timestamp with the portal display and known local time | `UNVERIFIED` |
| `PORTAL_DATE_FORMAT` | Exact raw date or timestamp format | Copy timestamp strings from a response without changing punctuation or ordering | `UNVERIFIED` |
| `PORTAL_NUMBER_LOCALE` | Decimal and thousands separators | Copy raw numeric values from JSON or HTML responses | `UNVERIFIED` |
| `PORTAL_CONSUMPTION_UNIT` | Unit attached to a reading | Capture the reading unit field or table label | `UNVERIFIED` |
| `PORTAL_READING_KIND` | Interval value versus cumulative counter | Compare successive readings and inspect portal labels; do not infer from field names | `UNVERIFIED` |
| `PORTAL_TIMEOUT_SECONDS` | Whether this compatibility setting is used by the client | Inspect current client configuration; no portal response fills it | Local compatibility value |
| `PORTAL_CONNECT_TIMEOUT_SECONDS` | Normal connection timing and acceptable local budget | Inspect the Network **Timing** panel for ordinary reads | Local policy informed by observation |
| `PORTAL_READ_TIMEOUT_SECONDS` | Normal response timing and acceptable local budget | Inspect the Network **Timing** panel for ordinary reads | Local policy informed by observation |
| `PORTAL_WRITE_TIMEOUT_SECONDS` | Normal login request timing and acceptable local budget | Inspect the login request timing | Local policy informed by observation |
| `PORTAL_POOL_TIMEOUT_SECONDS` | Local request-pool wait budget | Record only ordinary request overlap; do not generate load | Local policy |
| `PORTAL_MAX_CONCURRENCY` | Any naturally observed concurrency or throttling limit | Record `429`, `Retry-After`, or documented guidance; do not probe limits | `UNVERIFIED` |
| `PORTAL_MAX_RETRIES` | Which statuses are transient and safe to retry | Record naturally returned `408`, `429`, `5xx`, or equivalent responses | Local policy informed by observation |
| `PORTAL_REAUTH_COOLDOWN_SECONDS` | Whether repeated expiry recovery is rate-limited | Record normal recovery timing; do not repeatedly expire a session | Local policy informed by observation |
| `PORTAL_CIRCUIT_FAILURE_THRESHOLD` | Local protection threshold informed by transient failures | Record naturally observed transient failures; do not create failures deliberately | Local policy |
| `PORTAL_CIRCUIT_RESET_SECONDS` | Local recovery window after an upstream outage | Record natural recovery timing if it occurs | Local policy |
| `RATE_LIMIT_PER_MINUTE` | Local API request policy | Confirm product-side API usage requirements; no portal observation fills this | Local policy |
| `RATE_LIMIT_MAX_KEYS` | Local API key cardinality limit | Confirm deployment size; no portal observation fills this | Local policy |
| `SYNC_INTERVAL_SECONDS` | Local refresh schedule | Confirm acceptable refresh frequency; do not infer from portal behavior | Local policy |
| `SYNC_JITTER_SECONDS` | Local refresh jitter | Confirm acceptable spread for scheduled refreshes | Local policy |
| `METER_METADATA_TTL_SECONDS` | Local freshness budget for meter metadata | Confirm how long indexed metadata may be served before refresh | Local policy |
| `HIERARCHY_TTL_SECONDS` | Local freshness budget for hierarchy data | Confirm how long indexed hierarchy may be served before refresh | Local policy |
| `RECENT_CONSUMPTION_TTL_SECONDS` | Local freshness budget for recent readings | Confirm how long indexed recent readings may be served before refresh | Local policy |
| `CLOSED_HISTORY_TTL_SECONDS` | Local retention/freshness policy for closed history | Confirm the intended local retention behavior | Local policy |
| `MAX_DATE_RANGE_DAYS` | Local API date-range safety limit | Confirm acceptable client range; no portal observation fills this | Local policy |
| `MAX_RESPONSE_RECORDS` | Local API response-size safety limit | Confirm acceptable client response size | Local policy |
| `ALLOW_LIVE_SMOKE` | Local safety switch for the read-only smoke command | Set to `false` while configuring; set to `true` only for an intentional run | `false` by default |
| `LOG_LEVEL` | Local logging detail | Confirm the desired local/production logging level | `INFO` unless changed locally |

## Login capture

Record these values from one normal login:

| Observation | Value |
|---|---|
| HTTP method | `UNVERIFIED` |
| Request path | `UNVERIFIED` |
| Content type | `UNVERIFIED` |
| Username field | `UNVERIFIED` |
| Password field | `UNVERIFIED` |
| CSRF field or header | `UNVERIFIED` |
| Redirect chain | `UNVERIFIED` |
| Final response status | `UNVERIFIED` |
| Success body marker | `UNVERIFIED` |
| Success URL marker | `UNVERIFIED` |
| Session cookie name | `UNVERIFIED` |
| Cookie attributes | `UNVERIFIED` |
| Failed-login status | `UNVERIFIED` |
| Failed-login response shape | `UNVERIFIED` |

If CSRF is present, record its field/header name and where it is obtained. The current configuration does not contain a CSRF setting, so no CSRF behavior should be inferred before capture.

## Read captures

For each read, save a sanitized request/response pair:

| Read | Capture |
|---|---|
| Meter list | Method, path, query, body, content type, wrapper key, one record, pagination, count fields, nulls, duplicates |
| Meter detail | Method, path template, identifier placement, response shape, missing-record response, one record |
| Consumption | Method, path template, date parameters, cursor/page parameters, timestamp, value, unit, ordering, nulls, duplicate timestamps |
| Hierarchy | Method, path, flat/nested shape, node ID, parent ID, type, name, meter association, duplicates, missing parents, cycles |
| Bulk/export | Method, path, parameters, content type, cursor/page fields, included datasets, only if a normal read-only control exposes it |

## Session expiry capture

Use natural expiry or delete only your own session cookie in the browser. Record:

- status code;
- redirect target;
- stable login-page HTML marker;
- stable login URL marker;
- JSON error shape, if present;
- whether one login restores the read;
- whether the retried read remains unauthenticated.

## Rate capture

Record only ordinary behavior:

- response duration from the Network **Timing** panel;
- `429`, `503`, or another transient status;
- `Retry-After` value and format;
- documented request limits;
- any response slowdown before rejection.

Do not intentionally generate load or repeated failed logins.

## Completion rule

An item stays `UNVERIFIED` when the browser did not show it. Do not replace `UNVERIFIED` with a guessed route, field, value, unit, date format, count, or limit.
