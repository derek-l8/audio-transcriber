# Versioned manual transcript editing

Implemented a separate Edited layer. Users select a segment from Raw or Balanced,
edit text/uncertainty, and save a retained revision. Later edits build on the
latest Edited version; the source layers and all timing intervals remain fixed.
The edited segment's confidence becomes null. Revision history is read-only.
All four export formats accept Edited; JSON labels the layer and supplies
manual-edit attribution, revision/parent IDs and the source layer/hash.

## Save semantics

An OS file lock serializes edits within a session and releases when the process
exits. Expected-revision checking refuses a stale editor. Each snapshot is
written before the atomic session pointer publishes it. If publication fails,
the prior version remains current and the new file is retained as an orphan;
published history ignores orphan files. Draft text stays in the open dialog
when saving fails. Unsaved text is not persisted across forced UI termination.

Readers verify the source layer's SHA-256 and require timestamp equality with
that layer. These checks detect source/timing inconsistencies; they are not a
claim of cryptographic tamper resistance for user-edit files.

## One-host full lecture check

`Test-DesktopEditing.py` copied the already completed 47-minute CS lecture session
to a new ignored validation library. The original desktop downloads and the
previous completed session were left untouched. The helper supplied two
**synthetic validation edits**, clearly marked `[validation edit 1/2]`; these
are test inputs, not manually audited corrections or reference text.

`results.json` records:

- 726 segments and two saved revisions.
- Unchanged Raw/Balanced hashes and unchanged timing intervals.
- Earlier revision text retained and readable in the history dialog.
- Edited version survives closing/reopening the library.
- Text, Markdown, SRT and JSON exports are nonempty; JSON revision matches the
  saved revision. Export fixtures include no new inference or downloads.
- Offscreen window rendering captured and visually inspected. Native clicks,
  power-loss durability and forced-exit draft recovery were not tested.

The deterministic tests also cover an OS lock conflict/release, stale revisions,
pointer publication failure, orphan handling, unsafe pointers, a changed source
hash, tampered timestamps, empty edited segments, CLI Edited export, and the
dialog retaining its draft on save failure.

All media/transcripts/preview images remain in ignored `.scratch/edited-full`.
Changes are local, uncommitted and unpushed.

Final suite: 143 passed, 1 Windows symlink skip, 1 live test deselected.
Ruff lint/format pass (51 files); focused strict mypy passes six source files.
