# FilmCraft control server

FilmCraft ships a localhost automation server. It is **not** MCP — it is newline-delimited
JSON over a TCP socket. This is how you make the app do things you cannot do by writing
JSON, and how you verify a file you wrote actually opens.

## Starting it

```bash
TOKEN=$(python3 -c "import secrets;print(secrets.token_hex(32))")   # exactly 64 hex chars
FILMCRAFT_CONTROL_TOKEN=$TOKEN /Applications/FilmCraft.app/Contents/MacOS/FilmCraft \
  --control 51515 --data-dir /tmp/fcdata --no-recover project.fcproj &
```

| flag | meaning |
|---|---|
| `--control <port>` | start the server (or `FILMCRAFT_CONTROL_PORT`) |
| `--data-dir <dir>` | auto-save / recovery / logs go here — **always set this when probing** so the user's real data is untouched |
| `--no-recover` | skip the "unsaved changes" prompt |
| `--demo` / `--empty` | open the demo project / start empty |
| `--control-input-only` | only the control server may drive widgets |

Positional args are a `.fcproj` **or media files**, so you can open a project directly.

A token that is not 64 hex characters silently disables the server; check the log for
`control server listening on 127.0.0.1:`.

## Talking to it

One JSON object per line: `{"method":…,"token":…,"params":{…}}`.
Replies: `{"ok":true,"id":null,"result":…}` or `{"ok":false,"error":"…"}`.

Verified methods:

| method | params | returns |
|---|---|---|
| `ui.elements` | — | every widget: `{id,label,rect:[x,y,w,h]}` |
| `ui.click` | `{id}` or `{x,y}`, optional `{clicks:2}` | null |
| `ui.drag` | `{from:{x,y},to:{x,y}}` | null |
| `ui.type` | `{text}` | null |
| `ui.key` | `{key,modifiers:["cmd"]}` | null |
| `ui.scroll` | `{id}` or `{x,y}` | null |
| `ui.focus` | — | focused widget |
| `ui.screenshot` | optional `{id:"panel.Timeline"}` | `{path,width,height}` |

Element ids are stable and readable: `project.item.<id>`, `project.button.new-item`,
`project.newItem.file.newSequence`, `timeline.clip.<id>`, `timeline.track.V1.locked`,
`timeline.captionTrack.C1`, `text.captions.newTrack`, `text.captions.add`, `panel.Timeline`.

### Gotchas

- **The server only answers while the app renders frames.** If the window is backgrounded or
  a modal is up, calls time out. Reconnect and retry; relaunch if it stays stuck.
- `ui.click`/`ui.type` on a value widget often does nothing. Driving the UI is for coarse
  actions (create a sequence, add a caption track). **Set values by writing JSON**, not by
  typing into the app.
- `ui.key` with `cmd+s` returns `ok` but does **not** save. There is no scriptable save —
  get state out via the recovery snapshot instead.
- The command ids embedded in the binary (`file.saveAs`, `export.queue.add`, …) are the
  menu/shortcut registry. They are **not** callable as control methods.

## Learning schema you do not have: the recovery-snapshot trick

Preferences set `recoveryJournal: true, recoveryIntervalSeconds: 5`, so a few seconds after
any edit the app writes a **complete project** to:

```
<data-dir>/Recovery/<session>/snapshot.fcproj
```

So, to learn how FilmCraft represents anything:

1. Copy the user's project somewhere scratch. Never probe the real file.
2. Launch with `--control` and a throwaway `--data-dir`.
3. Make the app do the thing (drag a clip to the timeline, `text.captions.newTrack`, …).
4. Wait ~7s, read `snapshot.fcproj`, diff it.

That is how every field in `fcproj-schema.md` was confirmed.

## Verifying a file you wrote

Writing JSON is only half the job — prove it loads:

```bash
FILMCRAFT_CONTROL_TOKEN=$TOKEN FilmCraft --control 51515 --data-dir /tmp/v --no-recover out.fcproj &
sleep 9
grep -icE 'error|fail|invalid|missing' /tmp/v/Logs/filmcraft.log    # expect 0
```

then `ui.click {"id":"project.item.<seq>","clicks":2}` to open the sequence, count
`timeline.clip.*` in `ui.elements`, and `ui.screenshot` the Program panel to read the total
duration and confirm captions render.

## Before writing to a project the user has open

FilmCraft holds the project in memory; a later Cmd+S overwrites whatever you wrote. Always
`pgrep -f FilmCraft` and close it first, then reopen after writing.
