# Proposal history and retention

Every **Save draft** and **Generate PPTX + PDF** creates a numbered revision. Snapshots contain the full intake data and the calculated quote at that moment, together with author and timestamp. Export revisions additionally retain the exact ZIP bytes (PPTX, PDF, JSON, and manifest) and application/template versions. Nothing is sent to GitHub or another service to retain history.

The Version history section lets both authenticated users inspect a snapshot, download a saved export, or restore a previous revision. Restoring appends a new revision; it does not overwrite older history. Unsaved keystrokes are not retained. Saving is explicit and exporting saves automatically.

The UI sends the version it loaded with writes. If another session saved a newer revision, the server rejects the stale write with HTTP 409. Reload the current revision and reapply the desired changes. This check also applies to restore, export of an existing proposal, and deletion.

## Existing data

The migration preserves existing accounts and drafts, importing each existing draft as revision 1 with author `migration` and its original timestamp. Revisions overwritten before this feature existed cannot be recovered. Imported snapshots have no historical quote because that result was not previously stored. Subsequent saves and exports contain the calculated quote.

## Automatic compression

On startup and once every 24 hours while the server runs, JSON snapshot payloads strictly older than one calendar year are losslessly gzip-compressed in batches. February 29 uses February 28 for the preceding year's boundary. UTC timestamps define eligibility. The task catches up after downtime and is idempotent. Reads and restores transparently decompress snapshots and verify their SHA-256 digest.

ZIP exports already use DEFLATE compression from creation and retain their original bytes so historical downloads do not change. Current working drafts stay uncompressed for normal editing. Compression makes SQLite pages reusable; the database file is not automatically vacuumed/shrunk. No history is deleted automatically.

## Deletion

- **Delete revision:** removes a selected noncurrent revision and its saved exports, after typing `DELETE`. The current revision cannot be removed alone.
- **Delete this proposal and all history:** removes the current draft, all its revisions, and all saved exports, after typing `DELETE`.
- **Preview records older than two years:** reports a cutoff and exact counts of eligible revisions, exports and inactive proposals. Typing `DELETE OLD HISTORY` commits deletion. Old revisions on recently active proposals are removed, while their recent revisions and current draft remain. Proposals whose latest save/export/restore is older than the cutoff are removed entirely. If eligible records change after the preview, the operation is rejected and must be previewed again.

Deletion is transactional with cascading foreign keys and has no in-app undo. Both accounts have equal permission to delete. External backups and already downloaded documents are separate copies and are not erased by these actions. SQLite deletion is logical deletion, not forensic secure erasure. Retention of backups is an operational decision, separate from the application's history controls.

## Storage and backups

Drafts, revisions, exports and credentials all reside in the existing Docker volume's SQLite database. The README's SQLite backup command includes all of them. Budget disk space for exported files and back up regularly. Compression is not a backup.

The public repository contains only code and fictional fixtures. History databases, pre-migration backups and private example overrides remain ignored by Git.
