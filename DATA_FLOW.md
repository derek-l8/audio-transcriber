# Data flow and recovery

```
imported file (WAV/MP3/M4A/MP4)
  └─ validate (type, regular file, size, resolved path)
  └─ copy into session: source/original.<ext> + sha-256 fingerprint
       (moving/deleting the original can no longer break the session)

decode via media boundary
  ├─ mono 16 kHz PCM WAV → used directly
  └─ other container → selected or PATH-discovered FFmpeg binary
       fixed argument array, no shell, private temp dir,
       bounded stderr capture, cleanup on success and failure
  → decoded containers use work/normalized.wav; compatible WAV uses its preserved copy

chunk loop (bounded memory; only one chunk is resident)
  for each planned window (default 30 s chunk / 0 s overlap):
    read window frames → engine.transcribe_samples()
      OpenVINO GenAI returns chunks with real start_ts/end_ts seconds
      multilingual checkpoints are forced to English output
    offset to absolute source time, validate monotonicity/window bounds
    merge overlap: drop only duplicates that repeat tail text INSIDE the
      temporal overlap; legitimate repetition elsewhere is preserved
    record ChunkRecord(index, device_used, seconds, dropped_duplicates)
    atomically replace checkpoint.json

device selection (CPU default; Auto and manual overrides are explicit)
  Auto orders successful synthetic benchmarks fastest-first; a failing device records
  {requested_device, failed_stage, error_category} and the next verified
  device is tried. Manual selection does not fall back. The per-chunk device
  records successful requested-device generation, not an independent hardware query.

finalize
  raw transcript written first (create-once immutable)
  Balanced layer derived deterministically (+ explicit dictionary rules only)
  session status → ready; checkpoint.json and work files removed
  exports generated on demand into exports/ (no silent overwrite)
```

## Recovery semantics

- `SessionStore.recover_interrupted` can mark stale sessions `interrupted`, but
  the desktop does not invoke it automatically: another CLI worker may be active.
  After forced termination, confirm the worker has stopped before explicit CLI resume.
- `resume SESSION_ID` is always explicit; nothing auto-resumes.
- Resume validates source fingerprint, model id/revision/integrity, decoder
  identity, and chunking settings; a mismatch refuses resumed inference. Finalized (`ready`) sessions refuse resume — start a new session.
- Interruption before the first checkpoint rebuilds state from session metadata;
  between chunks resumes from the last durable checkpoint; during checkpoint
  writing the previous atomic version survives; after the final chunk but before
  finalization, resume finalizes without retranscribing anything. Resumed runs
  produce segment-identical raw transcripts to uninterrupted equivalents
  in the exercised short real-model sandbox and Windows workflows. Experimental
  pause strategies resume from their saved window plan; older fixed schema 1
  checkpoints are read and upgraded on save.

Raw JSON and preserved source audio are never overwritten. All metadata uses
atomic write-then-rename. Session identifiers are validated; paths cannot escape
the selected data directory. The default library is outside the repository;
a user override can still choose a checkout or cloud-synced folder. See
[Privacy](PRIVACY.md) before sharing data or reports.

## Review and cleanup versions

Manual corrections save a separate Edited revision and retain its history.
Selected cleanup runs automatically after desktop import/resume, or after CLI
transcription with `--cleanup light|medium`; Off skips it. AI cleanup reads Raw
in bounded source blocks, uses a separate local
text model/device, and publishes a complete AI version plus a retained snapshot.
Numeric/negation/size warnings retain the source block; they do not prove meaning
preservation. Cancelled/failed cleanup leaves the previous complete result
available, and rerunning starts again. AI timings refer to source blocks rather
than generated word alignment. Cleanup AUTO tries GPU and retries a failed GPU
block on CPU, recording devices/fallback; explicit choices stay strict.
Summarize reads Raw separately and retains formatted excerpt notes in Summary,
with separate history and no subtitle export. Exports select Raw, Balanced,
Edited, AI, Formatted, or Summary; failure leaves earlier outputs available.

Formatting follows optional cleanup and reads the resulting AI layer, or Raw
when cleanup is Off. Mostly prose uses local paragraph grouping without a model.
Mixed/Structured request a layout plan from the same text model, reusing the loaded
pipeline after cleanup. Every source passage must appear once in original order;
unsupported layouts become prose. Complete formatted versions have a separate
history and source hash. They are documents rather than aligned subtitles.
