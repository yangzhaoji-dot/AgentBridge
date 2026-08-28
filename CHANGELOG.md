# Changelog

## 0.3.0-dev

- Added a nonsecret SSH profile plus start, status, smoke-test, and stop
  workflow for the Relay/Connector tunnel path.
- Added an extension popup that explicitly selects one dedicated ChatGPT tab.
- Reworked response completion detection: it now prefers actual composer state
  and uses a conservative fallback instead of returning after 2.2 seconds of
  unchanged text.
- Added a per-request completion marker protocol for long or structured calls;
  the default MCP path now waits for an explicit final marker.
- Verified the completion change with a browser fixture that pauses mid-answer.

## 0.2.0-dev

- Added the server-side Relay, device pairing, and outbound local Connector.

## 0.1.0

- Initial local Codex-to-ChatGPT browser bridge.
