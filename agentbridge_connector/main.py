from __future__ import annotations

import uvicorn

from agentbridge_connector.app import create_app
from agentbridge_connector.settings import EdgeConnectorSettings


def main() -> None:
    settings = EdgeConnectorSettings.load()
    # The local connector deliberately binds only to loopback. The browser is
    # reached locally; the connector itself creates the outbound relay link.
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
