# Desktop playback and full local lecture validation

Added preserved-source audio playback, play/pause, elapsed/duration display,
seek slider and an explicit transcript-segment seek action. Playback handles
MP4 audio without showing video; changing transcript layers preserves position.
Closing the window stops audio and safely pauses any active inference worker.

## Sources and verification

Three user-supplied local MP4 recordings were accessible, fingerprinted and
decoded through their complete audio streams
with FFmpeg's error-fatal mode. All exited zero without error output:

| File | Container duration | Size |
|---|---|---|
| video.mp4 | 47:20.29 | 163,269,532 bytes |
| video (1).mp4 | 54:06.82 | 183,304,414 bytes |
| video (2).mp4 | 1:07:14.72 | 234,512,198 bytes |

`local-source-checks.json` contains SHA-256 fingerprints and audio decode results.
These are integrity/decode checks, not comparison with an authoritative published
hash and not full video decode. Original input files were not edited.

## Full lecture and playback

The desktop imported the complete `video.mp4`, with pinned tiny.en/CPU and
configured FFmpeg, requested a mid-session pause, then resumed. All 95 chunks
finished ready without reported fallback. Persisted inference time: 107.407
seconds for 2840.126 seconds of normalized audio. No reference transcript was
provided, so no WER or accuracy claim follows from this run.

The initial export check found an SRT error and its modal dialog blocked the
offscreen helper. The helper was stopped after inference had completed. The
completed session was then reopened to validate fixes without repeating inference.
`full-lecture-results.json` explicitly labels that final phase
`review-existing-session`; its 0.38-second elapsed value describes review checks,
not full lecture runtime. Pause chunk count and uninterrupted equivalence are
null because this final report did not capture those initial phases.

Final checks on the completed full session passed: all eight exports, search,
muted playback advancing after a middle-of-file seek, and transcript-segment
seek. Playback duration: 2,840,285 ms. Screenshot saved in ignored scratch data
and visually inspected. No audible listening, microphone test, native mouse
interaction, GUI memory profiling, or accuracy audit was performed.

## Separate short base-model run

A 90-second stream-copy excerpt starting at 600 seconds of `video (1).mp4`
completed GUI import, safe pause/resume, all eight exports, search and muted
playback/segment seek with base.en/CPU. Resumed segments exactly match a second
uninterrupted run. Three chunks each, zero reported fallback; 757 Qt timer
callbacks in 24.03 seconds. See `base-short-results.json`.

## Bugs exposed and fixed

- Windows access/sharing denial during atomic metadata replacement: bounded
  retries for Windows error codes 5/32/33, up to 620 ms of backoff. Persistent
  denial still raises and retains the previous file. Other errors do not retry.
  The affected base workflow passed after the fix; simulated transient/persistent
  failure tests verify preservation and retry bounds. Windows lock timing is
  variable, so this is not a guarantee that access errors can never recur.
- SRT timestamp rounding could emit `,1000` near a second boundary. Integer
  total-millisecond rounding now carries through seconds/minutes/hours.
- Empty transcript segments could disrupt SRT cue separators, including segments
  emptied by Balanced cleanup. SRT now omits empty segments and renumbers cues;
  blank lines inside nonempty cue text are removed. Stored layers remain intact.
- Resuming now persists `processing` before inference, rather than displaying
  the previous interrupted status throughout resumed work.

All media copies, transcripts and preview images remain in ignored
`.scratch/desktop-full`. Changes are local, uncommitted and unpushed.

Final network-free suite: 134 passed, 1 Windows symlink skip, 1 live test
deselected. Ruff lint/format pass (47 files), focused strict mypy passes six
source files, and whitespace checks pass. Tests cover retry bounds/file
preservation, SRT carry/empty cues, resumed processing status and Qt playback.
