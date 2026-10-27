# Sanitized portal reconnaissance notes

Generated on **2026-10-27** from `urja-ops.flockenergy.tech.har`.

Only request and response structure is recorded here. Credential values, cookie values, personal-looking values, and query/form values are redacted.

## Captured entries

| # | Method | Path | Status | Content type | Redirect | Query names | Form names | Pagination | CSRF names | Set-Cookie names/attributes | Response headers | Time (ms) | Timing details |
|---:|---|---|---:|---|---|---|---|---|---|---|---|---:|---|
| 1 | POST | `/login` | 200 | application/json | no | — | email, password | — | — | — | content-length, content-type, date | 336.3499999977648 | _blocked_queueing=5.35900000249967, _workerFetchStart=-1, _workerReady=-1, _workerRespondWithSettled=-1, _workerStart=-1, blocked=11.341000002499669, connect=-1, dns=-1, receive=7.870999979786575, send=3.373, ssl=-1, wait=313.76500001547856 |
| 2 | GET | `/meters/__data.json` | 200 | application/json | no | x-sveltekit-invalidated | — | — | — | — | cache-control, content-length, content-type, date | 172.51499998383224 | _blocked_queueing=0.5939999828115106, _workerFetchStart=-1, _workerReady=-1, _workerRespondWithSettled=-1, _workerStart=-1, blocked=1.3629999828115107, connect=-1, dns=-1, receive=1.0529999854043126, send=0.517, ssl=-1, wait=169.58200001561642 |
| 3 | GET | `/portal/meters/search` | 200 | application/json | no | page, q | — | page | — | — | content-length, content-type, date | 171.24100000364706 | _blocked_queueing=0.5799999926239252, _workerFetchStart=-1, _workerReady=-1, _workerRespondWithSettled=-1, _workerStart=-1, blocked=0.9379999926239252, connect=-1, dns=-1, receive=2.250000019557774, send=0.21799999999999997, ssl=-1, wait=167.83499999146537 |
| 4 | POST | `/api/auth/sign-out` | 200 | application/json | no | — | — | — | — | — | content-type, date | 169.27399998530746 | _blocked_queueing=0.6569999968633056, _workerFetchStart=-1, _workerReady=-1, _workerRespondWithSettled=-1, _workerStart=-1, blocked=1.0889999968633055, connect=-1, dns=-1, receive=1.0679999832063913, send=0.538, ssl=-1, wait=166.57900000523776 |

## Capture notes

- Redirect targets are recorded as paths only.
- Query and form values are intentionally omitted from this summary.
- Portal behavior remains `UNVERIFIED` until these structures are reviewed against the application contract.
