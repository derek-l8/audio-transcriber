# Data flow and recovery (Milestone 1 batch flow)

```
imported file (WAV/MP3/M4A/MP4)
  └─ validate (type, regular file, size, resolved path)
  └─ copy into session: source/original.<ext> + sha-256 fingerprint
       (moving/deleting the original can no longer break the session)

decode via media boundary
  ├─ mono 16 kHz PCM WAV → used directly
  └─ other container → configured FFmpeg binary
       fixed argument array, no shell, private temp dir,
       bounded stderr capture, cleanup on success and failure
  → normalized.wav inside the session work directory

chunk loop (bounded memory; only one chunk is resident)
  for each planned window (default 30 s chunk / 1 s overlap):
    read window frames → engine.transcribe_samples()
      OpenVINO GenAI returns chunks with real start_ts/end_ts seconds
      multilingual checkpoints are forced to English output
    offset to absolute source time, validate monotonicity/window bounds
    merge overlap: drop only duplicates that repeat tail text INSIDE the
      temporal overlap; legitimate repetition elsewhere is preserved
    record ChunkRecord(index, device_used, seconds, dropped_duplicates)
    atomically replace checkpoint.json

device fallback (automatic policy or manual override)
  verified benchmarks ordered fastest-first; a failing device records
  {requested_device, failed_stage, error_category} and the next verified
  device is tried; every completed chunk records its actual device;
  never silently labelled as another device.

finalize
  raw transcript written first (create-once immutable)
  Balanced layer derived deterministically (+ explicit dictionary rules only)
  session status → ready; checkpoint.json and work files removed
  exports generated on demand into exports/ (no silent overwrite)
```

## Recovery semantics

- Startup recovery marks stale `recording`/`processing` sessions `interrupted`.
- `resume SESSION_ID` is always explicit; nothing auto-resumes.
- Resume validates source fingerprint, model id/revision/integrity, decoder
  identity, and chunking settings; any mismatch fails clearly without touching
  data. Finalized (`ready`) sessions refuse resume — start a new session.
- Interruption before the first checkpoint rebuilds state from session metadata;
  between chunks resumes from the last durable checkpoint; during checkpoint
  writing the previous atomic version survives; after the final chunk but before
  finalization, resume finalizes without retranscribing anything. Resumed runs
  produce segment-identical raw transcripts to uninterrupted equivalents
  (verified with the real pinned model in the sandbox).

Raw JSON and preserved source audio are never overwritten. All metadata uses
atomic write-then-rename. Session identifiers are validated; paths cannot escape
the data directory. The repository is never a data directory.
