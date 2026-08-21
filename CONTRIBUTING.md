# Contributing

## Before changing an adapter

- Keep provider adapters text-only until a capability is explicitly added.
- Preserve one-request-at-a-time behavior unless the request protocol changes.
- Add or update a DOM fixture for every selector or completion-state change.
- Keep tokens, browser sessions, private prompts, and local logs out of commits.

## Before opening a pull request

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest
node --check .\extension\background.js
node --check .\extension\chatgpt_adapter.js
node --check .\extension\content.js
```

Describe the provider, browser version, tested page state, and failure mode for
any adapter change.
