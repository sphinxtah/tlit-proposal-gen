# Validation record

Validated locally on October 27, 2026.

- `tlit-proposal-gen-app-1` is healthy and bound to localhost port 8088.
- Ten automated test cases pass, covering sample totals, billing modes and proportional taxable discount allocation, invalid inputs, login/write protection, saved draft reload/update, ZIP contents, client-name replacement, blank payment fields, retained nonrenewal text, and long-content generation/pagination.
- Browser smoke test passed in Chrome: login, Example Company load, draft save, ZIP download, changing billing modes, and mobile width. No JavaScript runtime errors or mobile horizontal overflow.
- Generated example PDF: nine pages, every page rendered and visually reviewed. Schedule A, services, inventory, rates, signature blocks and blank payment authorization are present.
- Generated example PPTX: fifteen slides, rendered using PowerPoint. Source marketing slides retained; generated discovery, pricing and terms slides reviewed for fit.
- Sample math: $240 workstation support + $80 server support + $50 cybersecurity + $40 backup = $410 monthly. $500 setup gives $910 first month and $15,260 over 36 months at unchanged rates, before any applicable tax.
- Tax remains unreviewed/provisional in the example. No product-level tax classification was inferred automatically.
- Temporary browser-test user, session and draft removed. No default credentials remain.
- No deployment to Acadia has occurred. No existing unrelated Docker containers were started, stopped, edited or deleted.

Known limits: local account creation/reset is via CLI; stale draft saves are rejected; drafts allow exports with review warnings. The PDF's payment page preserves the source “7st” typo and existing fees pending a wording review. The static marketing deck contains original statistics/claims that need normal business approval before use.

History additions: tested migration idempotency, archived snapshot restore, exact export bytes, one-year/leap-year boundary, explicit deletion, bulk preview counts and confirmation guards. Browser test covers snapshot view, restore, historical download and individual revision deletion. Generated text slides re-rendered and reviewed with centered Arial text and the original TeamLogic IT logo header.

## v0.2.0 wizard validation (October 29, 2026)

- Image rebuilt with `docker compose -p tlit-proposal-gen up -d --build`; container healthy on localhost:8088.
- 17 automated tests pass inside the container (10 existing + 7 new in `tests/test_hardening.py`: security headers, rate-limit keying with/without `TRUST_PROXY`, client/revision export filenames, quoted `If-Match`, legacy-layout restore returns 422, session/attempt purge, wizard markup).
- Live browser walkthrough with a temporary account (removed afterwards, along with its test proposal): sign-in, example load, step gating without a client name, billing-model radio cards hiding irrelevant rate fields, save (revision 1), recap on Review & export, generate (revision 2, download named `TeamLogic-Proposal-<client>-r2.zip`), Version history panel listing both revisions. No JavaScript errors.
- Headless Chromium run against a stub API at desktop, tablet (1100px) and phone (390px) widths: no horizontal overflow, stepper collapses to numbered dots on narrow screens.
- `scripts/browser-smoke.cjs` was updated for the wizard but not executed on this host because Node is not on the PATH of the shell used; run it from a shell where `node` resolves.
