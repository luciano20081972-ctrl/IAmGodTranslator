# v11.5 Reader Lab

This lab is intentionally isolated from the production Reader. It uses synthetic fixture text only and does not import private Original, AI, or Reference chapters.

Current scope:

- Compare the existing escaped paragraph renderer with a Readium-inspired typography wrapper.
- Measure render time, HTML size, estimated DOM node count, and locator restore behavior.
- Exercise long-chapter and mobile viewport assumptions without changing production code.

Run:

```bash
python IAmGodTranslator_Render_Deploy/tools/reader_lab/reader_lab_benchmark.py
```

The benchmark is deterministic enough for regression checks, but it is not a replacement for Playwright visual QA.
