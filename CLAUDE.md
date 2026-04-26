## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

## Ubiquitous Language

This project has a canonical vocabulary defined in `UBIQUITOUS_LANGUAGE.md`.

Rules:
- Before using any domain term, verdict value, column name, or operator-facing string — read `UBIQUITOUS_LANGUAGE.md`
- Use only the canonical terms defined there (PASS, FAIL, GO, NO_GO, etc.)
- Do not invent synonyms or use the aliases listed in the "Aliases to avoid" column
