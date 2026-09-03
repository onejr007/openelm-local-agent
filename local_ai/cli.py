import argparse

import uvicorn

from .config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenELM local multi-project agent")
    parser.add_argument("serve", nargs="?", default="serve")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    settings = get_settings()
    uvicorn.run(
        "local_ai.api:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=False,
    )

