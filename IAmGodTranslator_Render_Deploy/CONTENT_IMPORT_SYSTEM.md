# GodTranslator v10.5 Content Import System

v10.5 makes Content Import Center the official onboarding workflow:

Create Novel -> Import Content -> Validate -> Preview -> Import -> Read -> Translate Optional.

Recovery remains a maintenance tool for filling missing data only.

## Admin Workflow

Admin -> Content -> Imports opens the Content Import Center.

The wizard supports:

- Existing novel or create new novel.
- Original, English, Reference, metadata, cover, and glossary imports.
- JSON payloads and ZIP/GodTranslator pack preview.
- Preview before write.
- Conservative default options: skip existing, add missing, merge metadata, import titles, dry run available.
- Execute summary with imported, updated, skipped, and error counts.

## API

- `POST /api/admin/content/import/preview`
- `POST /api/admin/content/import/execute`
- `POST /api/admin/content/import/preview-pack`
- `GET /api/admin/content/editions/{novel_id}`
- `POST /api/admin/content/editions/{novel_id}/{chapter_number}/default`

All endpoints require Admin.

## Safety

Preview is read-only. Dry run writes nothing. Execute creates or updates only the selected novel and chapter content. Existing content is preserved unless overwrite is explicitly enabled.

No OpenAI call is required for import. Fully translated novels with English content are readable immediately.
