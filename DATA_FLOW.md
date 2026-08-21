# Data flow and recovery

Imported media or microphone PCM is copied incrementally into the selected application
data directory. Decode/normalize produces bounded 16 kHz mono chunks. The speech engine
emits timestamped raw segments and provenance. Atomic checkpoints persist progress.
Deterministic cleanup creates a separate timestamped layer; optional local rewriting and
dictionary mappings create attributable processed output; user edits remain separate.

Raw JSON and lecture source audio are never overwritten. Metadata is written to a sibling
temporary file, flushed, and atomically replaced. Raw and cleaned transcript files are
create-once. On startup, sessions left in `recording` or `processing` become `interrupted`
and can be resumed or exported. Deletion will enumerate an exact session directory and
requires explicit confirmation.

The repository is never a data directory. Successful short-dictation audio is ephemeral;
failed audio may be retained visibly for a bounded period. Insertion will retain text in
history before attempting a target, reject known unsafe controls, verify focus, restore
the clipboard in `finally`, and expose copy fallback on every failure.
