# GodTranslator v11.5 Translation + Reader Design

Generic ebook readers cannot be the final product model for GodTranslator. The Reader must expose translation intelligence without becoming an admin dashboard.

## Design Principles

- Keep normal reading calm.
- Reveal translation tools only from selection, context, or explicit menus.
- Never expose Reference to unauthorized users.
- Never expose provider internals to normal users unless the data is intentionally productized.
- Preserve privacy and budget controls.
- Tie every translation action to a stable locator, not a transient scroll position.

## Differentiated Features

| Feature | Priority | Reader behavior | Required foundation |
| --- | --- | --- | --- |
| Tap/selection to show Original | CORE BEFORE V12 | Selection menu includes View Original for authorized/available source. | Paragraph/sentence locator and source variant adapter. |
| Tap/selection to show Reference | CORE BEFORE V12 FOR AUTHORIZED ROLES | Authorized users can compare selected AI text with Reference. | Reference permission boundary and selector model. |
| AI vs Reference compare | CORE BEFORE V12 | Compact compare panel for selected paragraph/chapter. | Alignment and authorization. |
| Sentence/paragraph alignment | CORE BEFORE V12 | Reader knows which Original segment corresponds to AI/Reference text. | Alignment storage or deterministic paragraph mapping. |
| Glossary definition popup | CORE BEFORE V12 | Selecting a term can show approved terminology. | Glossary API and selector context. |
| Recurring terminology inspection | USEFUL BEFORE V12 | Translator sees repeated terms and consistency risk. | Terminology extraction/evaluation. |
| Report translation issue | CORE BEFORE V12 | Current action becomes structured issue with locator/source/model context. | Web Annotation-style target plus issue type. |
| Regenerate selected paragraph | USEFUL BEFORE V12 | Translator/admin action only; preserves budget and audit trail. | Job item creation from locator, provider controls. |
| Alternate translation view | POST-V12 | Compare multiple AI editions. | Edition model and storage. |
| Translation provenance | CORE BEFORE V12 | Show edition/profile/model/date for chapter or selected paragraph. | Translation metadata and role-aware display. |
| Confidence/QA flags | USEFUL BEFORE V12 | Mark passages with quality warnings without clutter. | Evaluation pipeline. |
| Split bilingual mode | CORE BEFORE V12 | Side-by-side or interleaved Original/AI/Reference based on role. | Publication variants and alignment. |
| Hover/tap Chinese source | USEFUL BEFORE V12 | Popover shows source text for selected translated passage. | Alignment and mobile-friendly UI. |
| Quick glossary addition | USEFUL BEFORE V12 | Translator adds selected term/translation to glossary. | Role-gated glossary editor. |
| "Why translated this way?" | POST-V12 | Diagnostics summarize profile/glossary/evidence without leaking prompts. | Structured provenance and safe explanation layer. |
| Reader-linked evaluation | CORE BEFORE V12 | Reviewers can score or flag translation quality in context. | Evaluation records tied to locators. |

## Normal Reader Surface

Default Reader stays book-like:

- Chapter title
- Text
- Minimal toolbar/menu
- Contextual actions only after selection or long press

Translation intelligence appears as overlays, drawers, or inspector panels that can be dismissed.

## Role Matrix

| Capability | Guest | Reader account | Translator | Admin |
| --- | --- | --- | --- | --- |
| Read AI translation | yes, if public | yes | yes | yes |
| View Original | yes, if source is public | yes, if allowed | yes | yes |
| View Reference | no | no unless explicitly granted | yes | yes |
| Report issue | local/limited | yes | yes | yes |
| Add glossary term | no | no | yes | yes |
| Regenerate paragraph | no | no | role-dependent | yes |
| View provider/model diagnostics | no | limited provenance | yes | yes |

## Data Model Direction

Use a locator target for every Reader-linked translation object:

- novel id
- chapter number
- source variant
- paragraph index/id
- text quote context
- progression
- optional EPUB CFI later

This allows one selector to power bookmarks, highlights, translation issues, glossary examples, and evaluation records.

## Privacy And Safety

- Reference text remains protected at API and frontend levels.
- Provider prompts, secrets, raw request/response bodies, and private evaluation data must not appear in normal Reader metadata.
- Regeneration must respect budget and provider limits.
- Reader issue reports must not include private source/reference text unless the acting role is authorized and the destination is internal.
