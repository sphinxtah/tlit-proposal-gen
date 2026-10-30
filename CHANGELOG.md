# Changelog

## v0.2.0 — Wizard intake and hardening

- New proposals are entered through a seven-step wizard with a progress stepper, per-step validation, Back/Next navigation, deep-linkable steps and a Review & export recap with Edit links. Saved proposals open on the recap.
- Step 2 (Engagement) asks the qualifying questions up front: billing model, supported users/devices, term, MSA and SOW dates. Pricing only shows the rate fields for the chosen billing model; Inventory compares listed equipment against billed counts live.
- Version history moved to its own panel in the sidebar.
- API error bodies that are not JSON (gateway errors, oversized requests) now surface as readable messages instead of a parse failure; Pydantic validation errors are rendered field by field.
- Restoring a revision saved under an older data layout returns 422 with the offending fields instead of a 500.
- Login rate limiting can key on `X-Forwarded-For` when `TRUST_PROXY=true`; by default it still uses the socket address.
- Expired sessions and finished login-attempt windows are purged daily.
- Security headers (CSP, nosniff, frame denial, no-store on API responses) on every response.
- Export downloads are named after the client and revision, e.g. `TeamLogic-Proposal-Example-Company-r4.zip`.
- Quoted `If-Match` values from intermediaries are accepted.

## v0.1.0 — Initial release

- Client discovery, inventory, configurable pricing, scope, and local accounts.
- PowerPoint and PDF generation from shared calculations.
- Revision history for every explicit save and export, including author and timestamp.
- Retrieval of exact generated documents and restoration as a new revision.
- Automatic compression of history older than one calendar year, on startup and daily while running.
- Confirmed deletion of individual historical revisions or complete proposals.
- Preview and confirmed bulk deletion of history older than two calendar years, including inactive proposals.
- Optimistic concurrency checks prevent stale browser edits from overwriting newer revisions.
- Centered text, Arial typography, and a TeamLogic IT logo header bar on generated slides.
