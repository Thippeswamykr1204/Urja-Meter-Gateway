# Reflection

## What assumptions did you make?

I assumed the missing evidence block was intentional in this workspace rather than permission to guess the portal. The API therefore has a fixture-backed demo mode and an evidence-driven live adapter. I also assumed a small local catalog is useful for the take-home and that SQLite is an appropriate default while clearly marking the scale boundary.

## Which part was most difficult, and how did you get unstuck?

The hardest part was balancing the requested product surface with the absence of portal protocol evidence. I got unstuck by separating transport from parsing, making live paths configuration-only, and using sanitized fixtures to exercise the rest of the product without making false claims about the upstream system.

## If you had another day, what would you improve?

I would capture the live portal exchange, add exact replay fixtures for authentication and each data view, then tighten the parsers and contract tests against those observations. I would also add a background sync job, persisted consumption records, richer hierarchy validation, and a Postgres migration path for larger catalogs.

## What mistake did you make while solving this?

The first demo implementation accidentally tried to attach provenance to a consumption point even though provenance belongs to the response envelope. I removed that mismatch and kept record-level quality separate from response-level provenance.

## What would you criticise in your own submission?

The local demo is coherent, but it is not evidence of a working live integration because the required network capture is absent. The HTTP adapter also needs a real portal replay before it can be called production-ready, and the SQLite index currently stores meter metadata rather than a complete historical consumption index.
