# `.fcproj` schema (FilmCraft 0.14.x, `schema_version: 15`)

Plain JSON, serde-tagged. Verified by driving FilmCraft itself (see `control-protocol.md`),
not by guesswork.

## Time

Everything is an integer tick count.

```
TICK  = 254_016_000_000        # ticks per second
FRAME = TICK // fps            # 60fps -> 4_233_600_000
```

`start`, `duration`, `source_in` **must be whole multiples of FRAME** or the clip lands
off-grid. Media `duration` is often *not* frame-aligned (screen recordings are VFR), so the
usable length of a media item is `floor(info.duration / FRAME)` frames.

## Top level

```json
{"format":"filmcraft.project","schema_version":15,"generator":"FilmCraft 0.14.0",
 "project":{"name":…,"settings":…,"root":{"id":0,"name":…,"children":[{"Item":1}]},
            "items":{"1":…},"next_id":5},
 "view":{"open_sequences":[],"active_sequence":null,"sequences":{}}}
```

- `items` is a map of **string** id -> item. `root.children` lists `{"Item": <id>}`.
- `next_id` must exceed every id you use (clips and markers consume ids too).
- `view` is UI state. `SequenceView` is unverified — leave `view` exactly as above; the
  sequence still opens by double-clicking it in the Project panel.
- The recovery snapshot omits `view` entirely; a saved project includes it.

## ItemKind

`item.kind` is a single-key object: `Media`, `Sequence`, `Subclip`, `Bin`,
`AdjustmentLayer`, `Graphic`.

### Media

```json
{"id":1,"name":"clip.mov","label":"Violet","metadata":{},"created":1,
 "kind":{"Media":{"media":{"File":{"path":"/abs/path.mov"}},
   "info":{"name":…,"kind":"Movie","duration":<ticks>,
     "video":{"width":2880,"height":1800,"frame_rate":{"num":60,"den":1},"par":[1,1],
              "codec":"H.264 (Main)","pixel_format":"YUV 4:2:0 8-bit",
              "color":{"matrix":"Bt709","transfer":"Bt709","primaries":"Bt709","range":"Limited"},
              "has_alpha":false,"bitrate":11746377},
     "audio_streams":[],"container":"QuickTime","start_timecode":null,"file_size":148507549},
   "interpret":{"frame_rate":null,"par":null,"ignore_alpha":false,"invert_alpha":false},
   "mark_in":null,"mark_out":null,"markers":[],"offline":false,"proxy":null,
   "identity":{"size":148507549,"fingerprint":"176e812555d653d6"}}}}
```

`identity.fingerprint` is how FilmCraft relinks media — copy media items verbatim, never
synthesise them.

### Sequence

```json
{"kind":{"Sequence":{
  "settings":{"width":2880,"height":1800,"frame_rate":{"num":60,"den":1},"par":[1,1],
    "sample_rate":48000,"drop_frame":false,"preset":"2880x1800 60","audio_master":"Stereo",
    "preview_codec":"ProRes 422","max_bit_depth":false,"max_render_quality":false,
    "working_space":"Rec. 709",
    "color":{"working":"Rec709","wide_gamut":false,"auto_tone_map":true}},
  "video_tracks":[…],"audio_tracks":[…],
  "markers":[],"mark_in":null,"mark_out":null,"work_area":null,"start_timecode":0,
  "master_volume_db":0.0,"master_effects":[],
  "master_mixer":{"mode":"Read","output":null,"record_arm":false,"solo_safe":false,"input_map":"Stereo"},
  "submix_tracks":[],"caption_tracks":[]}}}
```

### Track (video and audio share the shape)

```json
{"id":5,"kind":"Video","name":"Video 1","items":[…],"transitions":[],
 "locked":false,"sync_lock":true,"enabled":true,"muted":false,"solo":false,
 "channels":"Stereo","volume_db":0.0,"pan":0.0,"effects":[],
 "mixer":{"mode":"Read","output":null,"record_arm":false,"solo_safe":false,"input_map":"Stereo"}}
```

`kind` is `"Video"` or `"Audio"`. Three of each is what the app creates by default.
`transitions` is unverified — leave it `[]` and use straight cuts.

### TrackItem (a clip on a track)

```json
{"id":12,"item":4,"name":"shown on the clip","label":"Violet",
 "start":0,"duration":88723555200000,"source_in":0,
 "speed":1.0,"reverse":false,"enabled":true,"link":null,"group":null,
 "effects":[…],"markers":[],"gain_db":0.0,"frame_hold":null,"scale_to_frame":false}
```

- `item` points at the media item id.
- `duration` is **timeline** length. `source_in` is the in-point in the source.
- Source consumed = `duration * speed`.

### Speed / time remap — verified

To play a source range of `N` frames at `k`x:

```
duration = (N / k) frames
speed    = k                        # float on the TrackItem
effects[time_remap].params.speed.value.Float = k * 100     # percent
```

All three must agree. Prefer `k` that divides `N` evenly; otherwise floor and lose a frame.

### Default effect stack

Every clip the app creates carries these three. Copy them verbatim:

```json
[{"effect":"motion","enabled":true,"params":{
   "anchor":{"value":{"Vec2":{"x":<w/2>,"y":<h/2>}}},"anti_flicker":{"value":{"Float":0.0}},
   "position":{"value":{"Vec2":{"x":<w/2>,"y":<h/2>}}},"rotation":{"value":{"Float":0.0}},
   "scale":{"value":{"Float":100.0}},"scale_width":{"value":{"Float":100.0}},
   "uniform_scale":{"value":{"Bool":true}}}},
 {"effect":"opacity","enabled":true,"params":{
   "blend":{"value":{"Choice":0}},"opacity":{"value":{"Float":100.0}}}},
 {"effect":"time_remap","enabled":true,"params":{"speed":{"value":{"Float":100.0}}}}]
```

### Marker

```json
{"id":13,"start":<ticks>,"duration":0,"name":"","comment":"",
 "kind":"Comment","color":"Green"}
```

`kind`: `Comment` | `Chapter` | `Segmentation` | `WebLink`. Lives on the sequence
(`markers`) or on a clip (`TrackItem.markers`).

### CaptionTrack / Caption

```json
{"id":30,"name":"Subtitle","format":"Subtitle","language":"en",
 "style":{"font":"Inter","size":54.0,"color":[255,255,255,255],"background":true,
   "background_color":[0,0,0,191],"align":"Center","anchor":"Bottom","margin":0.08,
   "line_spacing":1.25,"outline":0.0,"outline_color":[0,0,0,255]},
 "enabled":true,"locked":false,"sync_lock":true,
 "captions":[{"id":31,"start":<ticks>,"duration":<ticks>,"text":"…",
              "speaker":null,"cue_id":null,"settings":""}],
 "vtt_blocks":[]}
```

`align`: Left|Center|Right. `anchor`: Top|Middle|Bottom. Colours are `[r,g,b,a]` 0-255.

## Label colours

`Violet, Caribbean, Mango, Purple, Magenta, Tan, Green, Brown, Yellow, Forest`

## Thai / non-Latin text — important

The **video renderer draws Thai correctly**; the **egui UI chrome does not** (clip names and
caption rows in the timeline show as tofu boxes).

- Captions, titles, anything burned into the picture: Thai is fine.
- `TrackItem.name`, `Marker.name`, track names: keep to ASCII so they stay readable in the app.
