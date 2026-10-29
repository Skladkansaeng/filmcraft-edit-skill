#!/usr/bin/env python3
"""Read and write FilmCraft .fcproj files (schema_version 15 / FilmCraft 0.14.x).

Subcommands:
  media   <project>              list media items (id, duration, resolution) — write a plan with these
  show    <project>              show the sequences, clips, markers and captions in a project
  dump    <project> [--seq NAME] write the current edit back out as a plan.json
  apply   <plan.json>            build the sequence described by the plan into its project

An edit plan is the editing context: sections, each with source segments, a speed and
caption lines. See examples/plan.example.json. Everything else (ticks, frame alignment,
effect stacks, marker ids) is handled here.
"""
import argparse, copy, json, os, shutil, sys

TICK = 254_016_000_000


def frame(fps): return TICK // fps


def load(path):
    with open(path) as f:
        d = json.load(f)
    if d.get("format") != "filmcraft.project":
        sys.exit(f"{path}: not a FilmCraft project")
    if d.get("schema_version") != 15:
        print(f"warning: schema_version {d.get('schema_version')}, this tool knows 15",
              file=sys.stderr)
    return d


def save(d, path, backup=True):
    if backup and os.path.exists(path):
        n, i = path + ".bak", 1
        while os.path.exists(n):
            i += 1; n = f"{path}.bak{i}"
        shutil.copy2(path, n)
        print(f"backup: {n}")
    with open(path, "w") as f:
        json.dump(d, f, ensure_ascii=False)


def media_items(d):
    return {int(k): v for k, v in d["project"]["items"].items() if "Media" in v["kind"]}


def sequences(d):
    return {int(k): v for k, v in d["project"]["items"].items() if "Sequence" in v["kind"]}


# ---------------------------------------------------------------- builders

def _effects(w, h, speed):
    return [
        {"effect": "motion", "enabled": True, "params": {
            "anchor": {"value": {"Vec2": {"x": w / 2, "y": h / 2}}},
            "anti_flicker": {"value": {"Float": 0.0}},
            "position": {"value": {"Vec2": {"x": w / 2, "y": h / 2}}},
            "rotation": {"value": {"Float": 0.0}},
            "scale": {"value": {"Float": 100.0}},
            "scale_width": {"value": {"Float": 100.0}},
            "uniform_scale": {"value": {"Bool": True}}}},
        {"effect": "opacity", "enabled": True, "params": {
            "blend": {"value": {"Choice": 0}},
            "opacity": {"value": {"Float": 100.0}}}},
        {"effect": "time_remap", "enabled": True, "params": {
            "speed": {"value": {"Float": speed * 100.0}}}},
    ]


def _mixer():
    return {"mode": "Read", "output": None, "record_arm": False,
            "solo_safe": False, "input_map": "Stereo"}


def _track(tid, kind, name):
    return {"id": tid, "kind": kind, "name": name, "items": [], "transitions": [],
            "locked": False, "sync_lock": True, "enabled": True, "muted": False,
            "solo": False, "channels": "Stereo", "volume_db": 0.0, "pan": 0.0,
            "effects": [], "mixer": _mixer()}


DEFAULT_CAPTION_STYLE = {
    "font": "Inter", "size": 48.0, "color": [255, 255, 255, 255], "background": True,
    "background_color": [0, 0, 0, 200], "align": "Center", "anchor": "Bottom",
    "margin": 0.08, "line_spacing": 1.25, "outline": 0.0, "outline_color": [0, 0, 0, 255]}


def build(d, plan):
    """Build the plan's sequence into project dict `d`. Returns (seq_id, total_ticks)."""
    med = media_items(d)
    if not med:
        sys.exit("project has no media items")
    fps = plan.get("fps") or 60
    F = frame(fps)
    ref = med[min(med)]["kind"]["Media"]["info"]["video"]
    w, h = plan.get("width", ref["width"]), plan.get("height", ref["height"])
    name = plan.get("sequence_name", "Edit")

    nid = d["project"]["next_id"]

    def new_id():
        nonlocal nid
        nid += 1
        return nid - 1

    vt = [_track(new_id(), "Video", f"Video {i+1}") for i in range(3)]
    at = [_track(new_id(), "Audio", f"Audio {i+1}") for i in range(3)]

    pos, clips, marks, caps = 0, [], [], []
    for sec in plan["sections"]:
        speed = float(sec.get("speed", 1.0))
        label = sec.get("label", "Violet")
        segs = sec["segments"]
        a = pos
        for n, seg in enumerate(segs, 1):
            item = int(seg["item"])
            if item not in med:
                sys.exit(f"section {sec['name']!r}: no media item {item}")
            limit = med[item]["kind"]["Media"]["info"]["duration"] // F
            src = int(round(seg["in"] * fps))
            src_frames = int(round(seg["out"] * fps)) - src
            if src_frames <= 0:
                sys.exit(f"section {sec['name']!r}: segment {n} has out <= in")
            if src + src_frames > limit:
                sys.exit(f"section {sec['name']!r}: segment {n} runs past the media "
                         f"({src + src_frames} > {limit} frames)")
            dur = int(src_frames / speed)          # floor; timeline length
            if speed != 1.0 and src_frames % speed:
                print(f"note: {sec['name']} seg {n}: {src_frames}/{speed} is not whole, "
                      f"dropping {src_frames - int(dur * speed)} frame(s)", file=sys.stderr)
            clips.append({
                "id": new_id(), "item": item,
                "name": sec["name"] if len(segs) == 1 else f"{sec['name']} ({n}/{len(segs)})",
                "label": label, "start": pos, "duration": dur * F, "source_in": src * F,
                "speed": speed, "reverse": False, "enabled": True, "link": None,
                "group": None, "effects": _effects(w, h, speed), "markers": [],
                "gain_db": 0.0, "frame_hold": None, "scale_to_frame": False})
            pos += dur * F
        marks.append({"id": new_id(), "start": a, "duration": 0, "name": sec["name"],
                      "comment": sec.get("comment", ""), "kind": "Comment",
                      "color": sec.get("marker_color", "Green")})
        texts = sec.get("captions") or []
        span = (pos - a) // F
        for i, txt in enumerate(texts):
            st = a + (span * i // len(texts)) * F
            en = a + (span * (i + 1) // len(texts)) * F
            caps.append({"id": new_id(), "start": st, "duration": en - st, "text": txt,
                         "speaker": None, "cue_id": None, "settings": ""})

    vt[0]["items"] = clips
    ctracks = []
    if caps:
        style = dict(DEFAULT_CAPTION_STYLE, **plan.get("caption_style", {}))
        ctracks = [{"id": new_id(), "name": plan.get("caption_track_name", "Subtitle"),
                    "format": "Subtitle", "language": plan.get("caption_language", "en"),
                    "style": style, "enabled": True, "locked": False, "sync_lock": True,
                    "captions": caps, "vtt_blocks": []}]

    seq = {"id": None, "name": name, "label": plan.get("sequence_label", "Forest"),
           "metadata": {}, "created": 1,
           "kind": {"Sequence": {
               "settings": {"width": w, "height": h,
                            "frame_rate": {"num": fps, "den": 1}, "par": [1, 1],
                            "sample_rate": 48000, "drop_frame": False,
                            "preset": f"{w}x{h} {fps}", "audio_master": "Stereo",
                            "preview_codec": "ProRes 422", "max_bit_depth": False,
                            "max_render_quality": False, "working_space": "Rec. 709",
                            "color": {"working": "Rec709", "wide_gamut": False,
                                      "auto_tone_map": True}},
               "video_tracks": vt, "audio_tracks": at, "markers": marks,
               "mark_in": None, "mark_out": None, "work_area": None, "start_timecode": 0,
               "master_volume_db": 0.0, "master_effects": [], "master_mixer": _mixer(),
               "submix_tracks": [], "caption_tracks": ctracks}}}

    # replace a sequence of the same name, else append
    sid = next((i for i, v in sequences(d).items() if v["name"] == name), None)
    if sid is None:
        sid = new_id()
        d["project"]["root"]["children"].append({"Item": sid})
    seq["id"] = sid
    d["project"]["items"][str(sid)] = seq
    d["project"]["next_id"] = nid
    return sid, pos


def to_plan(d, seq_name=None):
    seqs = sequences(d)
    if not seqs:
        sys.exit("project has no sequence")
    sid, seq = next(((i, v) for i, v in seqs.items()
                     if seq_name in (None, v["name"])), (None, None))
    if seq is None:
        sys.exit(f"no sequence named {seq_name!r}")
    S = seq["kind"]["Sequence"]
    fps = S["settings"]["frame_rate"]["num"] // S["settings"]["frame_rate"]["den"]
    F = frame(fps)
    caps = S["caption_tracks"][0]["captions"] if S["caption_tracks"] else []
    secs, by_name = [], {}
    for c in S["video_tracks"][0]["items"]:
        base = c["name"].rsplit(" (", 1)[0] if c["name"].endswith(")") and "/" in c["name"] else c["name"]
        sec = by_name.get(base)
        if sec is None:
            sec = {"name": base, "label": c["label"], "speed": c["speed"],
                   "segments": [], "captions": [], "_a": c["start"], "_b": 0}
            by_name[base] = sec
            secs.append(sec)
        src = c["source_in"] // F
        n = int(round(c["duration"] // F * c["speed"]))
        sec["segments"].append({"item": c["item"], "in": round(src / fps, 3),
                                "out": round((src + n) / fps, 3)})
        sec["_b"] = c["start"] + c["duration"]
    for sec in secs:
        sec["captions"] = [x["text"] for x in caps if sec["_a"] <= x["start"] < sec["_b"]]
        del sec["_a"], sec["_b"]
    plan = {"project": None, "sequence_name": seq["name"], "fps": fps,
            "width": S["settings"]["width"], "height": S["settings"]["height"],
            "sections": secs}
    if S["caption_tracks"]:
        t = S["caption_tracks"][0]
        plan["caption_track_name"] = t["name"]
        plan["caption_language"] = t["language"]
        plan["caption_style"] = t["style"]
    return plan


# ---------------------------------------------------------------- cli

def fmt(t):
    s = t / TICK
    return f"{int(s)//60}:{s%60:05.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("media", "show"):
        sub.add_parser(c).add_argument("project")
    p = sub.add_parser("dump"); p.add_argument("project"); p.add_argument("--seq")
    p = sub.add_parser("apply")
    p.add_argument("plan"); p.add_argument("--project"); p.add_argument("--out")
    p.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()

    if a.cmd == "media":
        d = load(a.project)
        for i, v in sorted(media_items(d).items()):
            info = v["kind"]["Media"]["info"]; vid = info["video"]
            fps = vid["frame_rate"]["num"] / vid["frame_rate"]["den"]
            secs = info["duration"] / TICK
            print(f"{i:3}  {secs:8.3f}s ({int(secs)//60}:{secs%60:06.3f})  "
                  f"{vid['width']}x{vid['height']}@{fps:g}  "
                  f"audio={len(info['audio_streams'])}  {v['name']}")

    elif a.cmd == "show":
        d = load(a.project)
        for i, v in sorted(sequences(d).items()):
            S = v["kind"]["Sequence"]; cl = S["video_tracks"][0]["items"]
            tot = sum(c["duration"] for c in cl)
            print(f"[{i}] {v['name']}  {fmt(tot)}  clips={len(cl)} "
                  f"markers={len(S['markers'])} "
                  f"captions={sum(len(t['captions']) for t in S['caption_tracks'])}")
            for c in cl:
                print(f"   {fmt(c['start'])} +{fmt(c['duration'])}  item={c['item']} "
                      f"in={fmt(c['source_in'])} {c['speed']:g}x  {c['name']}")

    elif a.cmd == "dump":
        d = load(a.project)
        plan = to_plan(d, a.seq)
        plan["project"] = os.path.abspath(a.project)
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    elif a.cmd == "apply":
        with open(a.plan) as f:
            plan = json.load(f)
        proj = a.project or plan.get("project")
        if not proj:
            sys.exit("no project: pass --project or set \"project\" in the plan")
        d = load(proj)
        sid, tot = build(d, plan)
        out = a.out or proj
        save(d, out, backup=not a.no_backup)
        print(f"{out}: sequence {sid} \"{plan.get('sequence_name','Edit')}\" "
              f"{fmt(tot)}  ({len(plan['sections'])} sections)")
        print("open it by double-clicking the sequence in the Project panel")


if __name__ == "__main__":
    main()
