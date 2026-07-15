# GodTranslator v10.5 Chapter Editions

Reader-facing text is now organized as Editions.

Public tabs:

- English
- Original

Translator/Admin tabs:

- English
- Original
- Reference

Normal users do not need to know whether English came from AI, official text, human import, or editing.

## Compatibility

Existing `chapters.ai_text` is preserved. During additive migration, readable `ai_text` is mirrored into `chapter_editions` as:

- language: `en`
- edition type: `AI`
- edition key: `ai`
- default: true

The scheduler still writes `ai_text` for compatibility, and v10.5 also mirrors new translation results into `chapter_editions`.

## Edition Types

Supported types:

- AI
- Human
- Official
- Edited
- Imported
- Machine
- Community

Default English selection priority is Official, Edited, Human, Imported, AI, Machine, Community, unless Admin sets a default edition.

## Reader Behavior

The Reader requests `english`, `original`, or `reference`.

Old `ai` reader links remain compatible and resolve to English.

Reference remains protected for Translator/Admin only.
