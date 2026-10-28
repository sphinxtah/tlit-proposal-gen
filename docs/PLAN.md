# TeamLogic IT proposal generator

## First working version

One local web application serves the intake UI and a FastAPI JSON API. SQLite stores shared drafts and local accounts in a named Docker volume. Both document renderers receive the same validated proposal and Decimal pricing result. No client information leaves the instance to generate documents.

Included: client/contact information, cloud and identity discovery, backup/security/application notes, equipment inventory, user/device/combined pricing, discounts, per-line taxable flags, 36-month initial term, $500 onboarding, service coverage, saved drafts, local logins, editable PPTX and PDF exports. ZIP exports include source JSON and template version/review warnings for reproducibility.

The original reference files remain unchanged. `templates/proposal.pptx` retains the source marketing slides and artwork. Client-specific discovery, pricing and rate slides are generated as editable text/tables with pagination. `templates/terms.json` retains Schedule A verbatim. `templates/services.json` supplies editable reference scope. The PDF uses a new typeset layout and includes signature blocks and the blank payment form; payment data is not collected by the application.

## Findings that need business review

- Example Company: demo uses 3 workstations and 1 server. The reference deck contains $320 support, $50 cybersecurity (2 × $25, in a grouped object), and $40 backup (2 × $20), totaling $410/month.
- The new default initial term is 36 months as requested; the example's old term was one year. Renewal remains editable, initially 12 months. Schedule A's 90-day nonrenewal clause is retained and the form locks that value.
- The source cover's separate cancellation wording is not repeated as an unconditional cancellation right. Schedule A termination and the MSA remain controlling. Tal should confirm the intended cancellation policy before client use.
- Original Schedule A remains verbatim, including references to minimum requirements/policies and scope. Minimum requirements are not actually specified in the source Schedule C. Resolve this template gap before relying on the SOW.
- The source blank payment form says “7st” and has a 3% credit card charge, 15-day cancellation/change notice and $45 NSF charge. These terms are retained, including the source typo, pending an authorized wording update.
- Marketing statistics, certifications and awards are retained from the supplied deck, not independently verified.
- Reference scope contains server services marked Included and some backup/security items marked Not applicable. Review coverage for each client; product pricing does not automatically grant coverage.

## Architecture choices and research

- [FastAPI Docker guidance](https://fastapi.tiangolo.com/deployment/docker/): build on a regular Python base image; no separate Gunicorn layer needed for this small single-process service.
- [python-pptx presentations](https://python-pptx.readthedocs.io/en/stable/user/presentations.html): an existing PPTX can serve as an editable template, preserving its package structure and artwork.
- [ReportLab Platypus](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/): flowing paragraphs and repeatable tables support predictable multipage PDF layout without installing Office on Debian.
- [Compose project naming](https://docs.docker.com/compose/how-tos/project-name/): explicit `tlit-proposal-gen` project name isolates the stack's resources.

## Next increments

1. Tal reviews contract/template fidelity, scope wording and tax classification with the business's tax adviser.
2. Add a service catalog for Datto Endpoint Backup, AppRiver cloud-to-cloud backup, Sophos Endpoint Protection, Sophos email filtering and Sophos MDR. Define billing units, costs/margins, license minimums, included features, term restrictions and tax classification before setting defaults.
3. Deploy to the dedicated Debian 13 VM on Acadia, create the two local accounts, configure intranet HTTPS/DNS and backups, test restore.
4. Revision history, exact export retention, compression, deletion and conflict detection are implemented in v0.1.0; see HISTORY.md.
5. Add template approval/version management, per-line jurisdiction/rates if needed, PDF preview and optional e-signature integration.

## Explicit boundaries

The current framework uses one tax rate per proposal applied only to flagged lines, with proportional allocation of the monthly discount. It does not automatically determine taxability or jurisdiction. There is no vendor catalog, payment processing, e-signature, or password recovery email. Revision author/timestamps and exact exports are retained in SQLite. Exports are generated synchronously and held in memory; appropriate for two users, not bulk jobs. Backups must include the SQLite volume and templates. Signed documents remain external records.
