# Security Policy

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Use [GitHub Security Advisories](https://github.com/SynapsesOS/synapses-scout/security/advisories/new)
to report vulnerabilities privately. You can expect a response within 72 hours.

Please include:
- Description of the vulnerability and its potential impact
- Steps to reproduce
- Affected versions
- Any suggested mitigations (if known)

## Security Model

Synapses-Scout is a **local-first tool** — it processes content on your machine.

- The HTTP server binds to `127.0.0.1` only (localhost, not exposed to network)
- Web searches use DuckDuckGo (no account, no tracking) by default
- SQLite cache lives at `~/.synapses/scout.db` — local filesystem only
- Intelligence distillation calls a local Ollama instance via synapses-intelligence
- No telemetry, no analytics, no data collection

## Known Limitations

- Extracted web content is cached in plaintext in SQLite. If you extract sensitive pages,
  the content persists until cache TTL expires or you manually clear it.
- The Tavily search provider (optional) requires an API key and sends queries to an external service.
  DuckDuckGo (default) does not require an API key.
- Crawl4AI browser fallback runs Chromium locally. Only use on URLs you trust.
