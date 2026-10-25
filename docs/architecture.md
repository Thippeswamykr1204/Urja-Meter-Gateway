# Architecture

```mermaid
flowchart LR
  Browser[React console] -->|API key + JSON| API[FastAPI /api/v1]
  API --> Service[Catalog service]
  Service --> Store[(SQLite WAL + FTS5)]
  Service --> Port[PortalAdapter interface]
  Port --> Demo[Sanitized demo adapter]
  Port --> Live[Evidence-driven HTTP adapter]
  Live --> Portal[Urja Meter Ops]
```

The adapter owns transport, authentication, retry, and parsing. The service owns the public contract, local index access, provenance, and summaries. The web console only calls documented API routes.
