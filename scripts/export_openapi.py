#!/usr/bin/env python3
"""
Export FastAPI OpenAPI spec to docs/openapi.json for MkDocs embedding.
"""

import json
from pathlib import Path

from services.api.main import app


def main():
    out = Path("docs/openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
