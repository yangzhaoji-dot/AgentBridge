# Security Policy

## Supported version

Only the latest `main` branch is supported while AgentBridge remains pre-1.0.

## Report a vulnerability

Do not open a public issue for a vulnerability, token exposure, browser-session
problem, local-network exposure, or prompt-injection bypass.

Use a private GitHub security advisory after the repository is published, or
contact the repository maintainer privately. Include a minimal reproduction and
redact all credentials, session data, personal information, and private source
files.

## Security boundaries

AgentBridge is a local bridge. It must not expose its token endpoint or
WebSocket listener to an untrusted network. Web-AI output is untrusted input and
must not directly authorize local execution or file changes.
