# filmcraft-edit

A [Claude Code](https://claude.com/claude-code) skill for editing **FilmCraft** video
projects programmatically — cut and order clips, set per-clip speed, add section markers and
burned-in captions, then verify the file actually opens.

FilmCraft has no scripting API for editing. This skill works by writing the sequence JSON
into the `.fcproj` directly, and by driving the app's undocumented localhost control server
to prove the result loads.

## Install

```bash
git clone <this repo> ~/src/filmcraft-edit-skill
ln -s ~/src/filmcraft-edit-skill/.claude/skills/filmcraft-edit ~/.claude/skills/filmcraft-edit
```

Or drop the repo next to a project — Claude Code picks up `.claude/skills/` from the working
directory too.

Requires FilmCraft 0.14.x (project `schema_version: 15`), macOS, Python 3, and ffmpeg for
finding cut points.

## Use

Describe the edit you want; the skill takes it from there. Under the hood the whole edit is
one JSON **plan**:

```json
{"project": "/abs/Project.fcproj", "sequence_name": "Tutorial Cut", "fps": 60,
 "sections": [
   {"name": "1 - Prep", "label": "Caribbean", "speed": 3.0,
    "segments": [{"item": 4, "in": 44.0, "out": 80.0}],
    "captions": ["ขั้นที่ 1 · เตรียมข้อมูลให้ตรง format"]}]}
```

`in`/`out` are seconds in the **source**. Timeline positions, tick math, frame alignment,
markers and caption spacing are computed for you.

```bash
S=.claude/skills/filmcraft-edit/scripts

python3 $S/fcproj.py media  Project.fcproj      # media item ids, durations, has-audio
python3 $S/fcproj.py apply  plan.json           # build the sequence (backs up first)
python3 $S/fcapp.py  verify Project.fcproj      # open it for real; log + clip count + screenshot
python3 $S/fcproj.py dump   Project.fcproj      # read the edit back out as a plan
```

Revisions are dump → edit the plan → apply. Round-tripping is exact, so "make the intro 3x"
is a one-field change, not a recalculation against already-sped-up clips.

## What's documented here

Both reference files were produced by making FilmCraft itself emit the answer — not by
guessing at field names.

- [`reference/fcproj-schema.md`](.claude/skills/filmcraft-edit/reference/fcproj-schema.md) —
  the `.fcproj` format: tick math, `Sequence`/`Track`/`TrackItem`/`Marker`/`Caption`, the
  verified speed formula, the default effect stack.
- [`reference/control-protocol.md`](.claude/skills/filmcraft-edit/reference/control-protocol.md) —
  the `--control` JSON-lines server: methods, element ids, what works and what silently
  doesn't, and the recovery-snapshot trick for learning schema you don't have.

## Known limits

- Straight cuts only. `Transition`, graphics/titles and `SequenceView` are **unverified**, so
  the tooling refuses to invent them. `fcapp.py probe` is the documented path to extend this.
- Non-Latin text renders correctly **in the video** but shows as tofu boxes in FilmCraft's own
  UI. Keep Thai in captions; keep clip and marker names ASCII.
- The sequence lands in the project bin but is not auto-opened — double-click it.
- Close FilmCraft before writing: it holds the project in memory and a later save overwrites you.

## Licence

MIT
