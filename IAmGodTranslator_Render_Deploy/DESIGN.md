# IAmGodTranslator Design Notes

## Product Direction

IAmGodTranslator is a reader-first PWA with translation, import, and admin tools behind the reading experience. The active visual identity is Dark Hour: a premium dark editorial interface with restrained cyan accents, book-like surfaces, and mobile-first safe-area behavior.

## Current Design Sources

- TasteSkill audit-first workflow: review the existing product, preserve strong identity decisions, and refine only the surfaces that block polish or usability.
- Vercel Web Interface Guidelines: prioritize fast perceived performance, clear navigation state, keyboard/touch accessibility, responsive layout, and useful content before background network work completes.
- Playwright browser checks: validate screenshots, console errors, overflow, offline shell behavior, and route timing with real browser automation rather than static inspection alone.
- AwesomeDesign / `awesome-design-md`: use project-local `DESIGN.md` files as machine-readable design governance. This project keeps its own Dark Hour rules instead of importing another product's style guide.

## v11.6.1 Startup Rule

The Home route must render useful reader content immediately from local memory, localStorage, or the static app shell. Network refreshes for the novel catalog, account Home, activity, admin, and translation operations are secondary and must not block the first useful paint.

## UI Guardrails

- Keep the chapter and reading path visually dominant.
- Avoid dashboard-first Home composition for guest and reader flows.
- Use the Dark Hour palette and existing tokens before adding new visual primitives.
- Preserve visible focus states, 44px mobile touch targets, readable disabled states, and safe-area padding.
- Do not add new branding strings outside the existing brand configuration unless the static startup shell needs a temporary no-JavaScript fallback.
