"""Production API process entry point."""

from __future__ import annotations

import uvicorn

from .config import Settings


def main() -> None:
    settings = Settings.load()
    uvicorn.run(
        "source_recall.api:create_app",
        host=settings.service.host,
        port=settings.service.port,
        workers=1,
        access_log=False,
        factory=True,
    )


if __name__ == "__main__":
    main()
