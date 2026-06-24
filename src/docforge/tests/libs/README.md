# Shared test building blocks

Reusable, cross-tier code — **no test logic here**, only the common bricks tests compose.

- `live_client.py` — `LiveClient`: a synchronous HTTP / multipart / Qdrant / SSE client that drives
  the **running** stack over its published ports. Used by the live tier (`live_test/`). Pure
  transport, no domain imports, so it stays decoupled from the application code under test.
