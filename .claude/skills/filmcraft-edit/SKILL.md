---
name: filmcraft-edit
description: Edit FilmCraft .fcproj projects by writing the timeline directly - cut and order clips, set per-clip speed, add section markers and burned-in captions (Thai included), then verify the file really opens. Use for any "cut this footage", "edit this video", "build a tutorial from these screen recordings", "speed up that section", "add subtitles" request involving FilmCraft or an .fcproj file.
---

# Editing FilmCraft projects

FilmCraft has no scripting API for editing. The way to edit is to **write the sequence JSON
into the `.fcproj` yourself**, then **open the result in FilmCraft to prove it loads**. Both
halves matter — a file that looks right but will not open is worse than no file.

Two scripts do the work:

| | |
|---|---|
| `scripts/fcproj.py` | read/write `.fcproj`: `media`, `show`, `dump`, `apply` |
| `scripts/fcapp.py`  | drive the app: `verify`, `launch`, `call`, `elements`, `shot`, `probe` |

Reference, read when you need the detail:
- `reference/fcproj-schema.md` — every field, tick math, speed formula, the Thai-text rule
- `reference/control-protocol.md` — the control server, and how to learn schema you lack

## The editing context: an edit plan

The whole edit is one JSON file — sections, each with source segments, a speed and caption
lines. `fcproj.py apply` turns it into a sequence. See `examples/plan.example.json`.

```json
{"project": "/abs/Project.fcproj", "sequence_name": "Tutorial Cut", "fps": 60,
 "sections": [
   {"name": "1 - Prep", "label": "Caribbean", "speed": 3.0,
    "segments": [{"item": 4, "in": 44.0, "out": 80.0}],
    "captions": ["ขั้นที่ 1 · เตรียมข้อมูลให้ตรง format"]}]}
```

- `in`/`out` are **seconds in the source**, not the timeline. Clips are laid end to end in
  order; starts are computed, never written by hand.
- `speed` 2.0 = twice as fast. Source consumed stays `in`→`out`; timeline length shrinks.
- `captions` are spread evenly across the section. One line = the whole section.
- Each section gets a marker at its first frame, named after the section.
- `label` tints the clips so sections are visible at a glance: Violet, Caribbean, Mango,
  Purple, Magenta, Tan, Green, Brown, Yellow, Forest.

Re-reading a plan back out of a project is `fcproj.py dump`, which round-trips exactly. For
a revision — "faster", "split that step by skill", "shorten section 1" — **dump, edit the
plan, apply**. Do not hand-patch ticks in the project; recomputing speed from an
already-sped-up clip is how you get a double-speed accident.

## Workflow

1. **See what you have.** `fcproj.py media <project>` lists item ids, durations,
   resolution and whether there is any audio. Those ids are what `segments[].item` means.

2. **Find the cut points.** The media is on disk; use ffmpeg, not guesswork:
   ```bash
   ffmpeg -ss 120 -i clip.mov -frames:v 1 -vf scale=1568:-1 -y f.png   # read it
   ffmpeg -i clip.mov -vf "scale=480:-1,select='gt(scene,0.25)',metadata=print:file=s.txt" \
          -an -f null -                                                # scene changes
   ```
   Reading one frame per candidate boundary at ~1568px wide is legible enough to tell what
   is on screen. Crop a strip (`crop=2880:380:0:300`) and `tile=1x8` to map many timestamps
   in one image when you only need "which screen is this".

3. **Write the plan**, then `fcproj.py apply plan.json`. It backs the project up, checks
   every segment against the real media length, and warns on frames lost to rounding.

4. **Verify.** `fcapp.py verify <project>` — launches isolated, opens the sequence, counts
   clips, greps the log, screenshots the Program monitor. **Read that screenshot**: it shows
   the total duration and whether captions render. Non-zero log errors = the file is wrong.

5. **Hand it back.** Open it for the user with `fcapp.py launch <project>` and tell them the
   sequence opens by double-clicking it in the Project panel.

## Rules that bite

- **Close FilmCraft before writing.** It holds the project in memory and a later Cmd+S
  overwrites you. `fcapp.py verify` refuses to run while an instance is up.
- **Thai (and any non-Latin script) renders in the video but not in the app's UI.** Put Thai
  in `captions`; keep `name` fields ASCII or the timeline shows tofu boxes. This is a FilmCraft
  UI font limitation, not an encoding bug — do not "fix" it by re-encoding.
- **Frame alignment is not optional.** Pick speeds that divide the segment's frame count
  evenly (at 60fps a 36.0s segment is 2160 frames: 2x and 3x are clean, 4x is not).
  `apply` floors and tells you what it dropped.
- **Screen recordings are usually VFR**, so media duration is not a whole number of frames.
  Never cut right up to the last frame.
- **Silent footage stays silent.** Check `audio=0` in `fcproj.py media` before promising
  anything about narration or cutting to speech.
- `view.sequences` is left empty because `SequenceView` is unverified. The sequence is in the
  bin, not auto-opened. Say so rather than letting the user think the timeline is empty.

## When the schema does not cover it

Transitions, titles, graphics, `SequenceView` — unverified, so do not invent fields. Learn
them the same way the rest was learned: `fcapp.py probe <project>` copies the project, opens
it isolated, and points you at the recovery snapshot the app rewrites every 5 seconds. Make
the app do the thing through `fcapp.py call ui.click ...`, wait, diff the snapshot.
`reference/control-protocol.md` has the detail, including which UI actions actually work
(coarse clicks do; typing into value fields does not).
