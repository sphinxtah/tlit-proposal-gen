# Changelog

## v0.3.0 — Reference-faithful documents

- Proposal slides 11–13 (Current State, Pricing, Hourly Rates) are now the original reference slides with client values filled in, instead of generated text slides. Generated decks match the reference deck exactly for the ProjectCenter data.
- Slide numbers ("11 / 14") removed from every slide.
- The managed services agreement is generated as a Word document from the original SOW (cover page, Schedules A–C, payment form) instead of a re-typeset PDF. `reportlab` and `pypdf` are no longer dependencies; `python-docx` is.
- Export ZIP entries are named like the reference files: `<Client>_IT_Proposal.pptx` and `TeamLogicIT - Managed IT Services-<Client>.docx`.
- New wizard inputs: current-state bullets, managed networks and mobile devices, backup card label, and per-charge Card (Cybersecurity / Backup / Other) and Unit. Older drafts get a Card guessed from the charge description.
- Review warnings when a charge, discount or tax would not be itemised on the pricing slide.
- `scripts/prepare_templates.py` rewritten to tokenise both originals and refuse to write templates that still contain client data.

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
