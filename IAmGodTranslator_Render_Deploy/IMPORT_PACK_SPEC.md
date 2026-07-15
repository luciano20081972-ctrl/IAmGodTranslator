# GodTranslator v10.5 Import Pack Spec

Import packs are ZIP files with a `manifest.json` and chapter text files.

Supported formats:

- `godtranslator-import-pack-v1`
- `godtranslator-original-pack-v1`
- `godtranslator-english-pack-v1`
- `godtranslator-reference-pack-v1`
- `godtranslator-mixed-pack-v1`
- `godtranslator-downloader-pack-v1`
- `godtranslator-new-novel-pack-v1`

## Manifest Fields

Required:

- `format`
- `novel_id`
- `chapters`

Recommended:

- `content_type`: `original`, `english`, `reference`, or `mixed`
- `edition_type`: `AI`, `Human`, `Official`, `Edited`, `Imported`, `Machine`, or `Community`
- `language`
- `novel`
- `metadata`

Chapter entries support:

- `chapter_number`
- `content_type`
- `edition_type`
- `language`
- `title`
- `source_url`
- `file`
- `sha256`
- `character_count`

## Example

```json
{
  "format": "godtranslator-mixed-pack-v1",
  "novel_id": "example-novel",
  "content_type": "mixed",
  "edition_type": "Official",
  "language": "en",
  "chapters": [
    {
      "chapter_number": 1,
      "content_type": "original",
      "title": "Chapter 1",
      "file": "original/0001.txt",
      "sha256": "..."
    },
    {
      "chapter_number": 1,
      "content_type": "english",
      "edition_type": "Official",
      "title": "Chapter 1",
      "file": "english/0001.txt",
      "sha256": "..."
    }
  ]
}
```

## Exclusions

Packs must never include passwords, API keys, cookies, browser profiles, access tokens, refresh tokens, `.env` files, logs, local databases, or production credentials.
