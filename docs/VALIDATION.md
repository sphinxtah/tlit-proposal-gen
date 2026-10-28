# Validation record

Validated locally on October 27, 2026.

- `tlit-proposal-gen-app-1` is healthy and bound to localhost port 8088.
- Five automated test cases pass, covering sample totals, billing modes and proportional taxable discount allocation, invalid inputs, login/write protection, saved draft reload/update, ZIP contents, client-name replacement, blank payment fields, retained nonrenewal text, and long-content generation/pagination.
- Browser smoke test passed in Chrome: login, Example Company load, draft save, ZIP download, changing billing modes, and mobile width. No JavaScript runtime errors or mobile horizontal overflow.
- Generated example PDF: nine pages, every page rendered and visually reviewed. Schedule A, services, inventory, rates, signature blocks and blank payment authorization are present.
- Generated example PPTX: fifteen slides, rendered using PowerPoint. Source marketing slides retained; generated discovery, pricing and terms slides reviewed for fit.
- Sample math: $240 workstation support + $80 server support + $50 cybersecurity + $40 backup = $410 monthly. $500 setup gives $910 first month and $15,260 over 36 months at unchanged rates, before any applicable tax.
- Tax remains unreviewed/provisional in the example. No product-level tax classification was inferred automatically.
- Temporary browser-test user, session and draft removed. No default credentials remain.
- No deployment to Acadia has occurred. No existing unrelated Docker containers were started, stopped, edited or deleted.

Known limits: local account creation/reset is via CLI; simultaneous draft edits use last-save-wins; drafts allow exports with review warnings. The PDF's payment page preserves the source “7st” typo and existing fees pending a wording review. The static marketing deck contains original statistics/claims that need normal business approval before use.
