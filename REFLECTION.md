# Reflection

## What assumptions did you make?

I assumed the portal should be treated as read-only and that unsupported upstream values must remain unknown rather than being normalized by guesswork. I chose a fixture-backed demo mode so the API and console remain usable without claiming that local examples came from the live system. I also chose SQLite because the brief allows a local index and the take-home is designed to run on one developer machine.

## Which part was most difficult, and how did you get unstuck?

The most difficult part was separating product behavior that can be demonstrated locally from portal behavior that still needs browser capture. I kept transport, parsing, storage, and API contracts separate. That lets the local product demonstrate search, freshness, quality, hierarchy, and failure handling while the live adapter refuses empty or unverified portal configuration.

## If you had another day, what would you improve?

I would capture the login exchange and each read request first, then replace the local examples with sanitized replays of the actual HTML, JSON, headers, expiry response, and pagination behavior. I would use those captures to add endpoint contract checks and parser golden tests. I would also expand the browser suite and measure the SQLite index with larger synthetic datasets before choosing a storage migration boundary.

## What mistake did you make while solving this?

The first demo implementation tried to attach response provenance to an individual consumption point. Provenance belongs to the response envelope, while quality belongs to each record. The model boundary and tests now keep those concepts separate.

## What would you criticise in your own submission?

The local product is coherent, but it is not proof of a working live integration because the portal exchange has not been captured. The HTTP adapter is deliberately conservative, yet it still needs real replay data before it can be called production-ready. The frontend is more complete than the current browser suite, and the scale boundary is described but not yet measured with the requested benchmark.
