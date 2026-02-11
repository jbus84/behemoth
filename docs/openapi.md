# OpenAPI (Embedded)

This page renders the **live OpenAPI spec** from `docs/openapi.json`.

**Generate spec locally**
```bash
make docs-openapi
```

Then run:
```bash
make docs
```

If you prefer the FastAPI hosted view, use:
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

---

<redoc spec-url="openapi.json"></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
