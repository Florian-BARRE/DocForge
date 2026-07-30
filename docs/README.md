# DocForge documentation

Start here. New to DocForge? Read **[Getting started](getting-started.md)** first.

## Guides

| Guide | For |
|---|---|
| **[Getting started](getting-started.md)** | Install, run the stack, first collection → upload → search. |
| **[REST API](rest-api.md)** | Every endpoint, authentication, curl examples. |
| **[Python SDK](python-sdk.md)** | `docforge-sdk` (async + sync) — per-resource reference. |
| **[MCP server](mcp.md)** | Drive DocForge from an AI model; the tool catalogue. |
| **[Architecture](architecture.md)** | The graph engine, packages, retrieval, quality gates. |
| **[Configuration](configuration.md)** | Every environment variable, per service. |
| **[Deployment](deployment.md)** | Production hardening, ports, secrets, GPU. |

## Reference

| Doc | Scope |
|---|---|
| [../src/docforge-rework/PIPELINE.md](../src/docforge-rework/PIPELINE.md) | The living pipeline reference — the 7 stages, every node, artefact and decision. |
| [../SPEC-docforge-document-intelligence-platform.md](../SPEC-docforge-document-intelligence-platform.md) | The full design specification. |
| [metadata-architecture.md](metadata-architecture.md) | Metadata schema, field origins, filterable / lexical / semantic surfaces. |
| [deployment-resources.md](deployment-resources.md) | Per-service CPU/RAM ceilings & resource strategy. |
| [PROD-HARDENING.md](PROD-HARDENING.md) | The exhaustive pre-go-live runbook. |
| [api/](api/) | Endpoint notes: collections, collections-config, discovery, capabilities. |

## Design records

`rpi/` holds the research → plan → implement records for still-live components (auth, dynamic batching,
chunk metadata, recursive discovery). `archive/` keeps history from the retired static-engine product.
These are design history, not user documentation.
