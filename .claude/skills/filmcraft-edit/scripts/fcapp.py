#!/usr/bin/env python3
"""Drive FilmCraft through its localhost control server.

  verify  <project>            launch isolated, open the sequence, check the log, screenshot
                               — run this after every write
  launch  <project>            start an instance you can keep talking to
  call    <method> [json]      raw control call, e.g. call ui.click '{"id":"project.item.1"}'
  elements [substr]            list widget ids (optionally filtered)
  shot    [--id panel.Timeline] [--out f.png]
  probe   <project>            copy the project, open it isolated, and tell you how to read
                               the recovery snapshot (for learning schema you do not have)
  quit                         stop the instance this tool launched

Session state (port + token) lives in $TMPDIR/fcapp-session.json.
"""
import argparse, json, os, secrets, shutil, socket, subprocess, sys, tempfile, time

APP = "/Applications/FilmCraft.app/Contents/MacOS/FilmCraft"
STATE = os.path.join(tempfile.gettempdir(), "fcapp-session.json")


def _state(**kw):
    if kw:
        json.dump(kw, open(STATE, "w"))
        return kw
    if not os.path.exists(STATE):
        sys.exit("no session — run `fcapp.py launch <project>` first")
    return json.load(open(STATE))


def call(method, params=None, port=None, token=None, timeout=30, retries=3):
    s = _state() if port is None else {"port": port, "token": token}
    last = None
    for _ in range(retries):
        try:
            c = socket.create_connection(("127.0.0.1", s["port"]), timeout=timeout)
            f = c.makefile("rwb")
            f.write((json.dumps({"method": method, "token": s["token"],
                                 "params": params or {}}) + "\n").encode())
            f.flush()
            r = json.loads(f.readline().decode())
            c.close()
            if r.get("ok"):
                return r.get("result")
            last = r.get("error")
        except (socket.timeout, OSError, ValueError) as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(1.5)
    raise RuntimeError(f"{method}: {last}\n"
                       "(the server only answers while the app renders — if the window is "
                       "backgrounded or a modal is open, calls time out)")


def launch(project, port=51515, data_dir=None, wait=9, extra=()):
    token = secrets.token_hex(32)
    env = dict(os.environ, FILMCRAFT_CONTROL_TOKEN=token)
    cmd = [APP, "--control", str(port), "--no-recover"]
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
        cmd += ["--data-dir", data_dir]
    cmd += list(extra) + [os.path.abspath(project)]
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(wait)
    _state(port=port, token=token, pid=p.pid, data_dir=data_dir or "", project=project)
    return p.pid, token


def running():
    return subprocess.run(["pgrep", "-f", "FilmCraft.app/Contents/MacOS/FilmCraft"],
                          capture_output=True, text=True).stdout.split()


def first_sequence(project):
    d = json.load(open(project))
    for k, v in d["project"]["items"].items():
        if "Sequence" in v["kind"]:
            return int(k), v["name"]
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("verify", "launch", "probe"):
        q = sub.add_parser(c)
        q.add_argument("project")
        q.add_argument("--port", type=int, default=51515 if c == "launch" else 51599)
        q.add_argument("--data-dir")
    q = sub.add_parser("call"); q.add_argument("method"); q.add_argument("params", nargs="?")
    sub.add_parser("elements").add_argument("substr", nargs="?")
    q = sub.add_parser("shot"); q.add_argument("--id"); q.add_argument("--out", default="shot.png")
    sub.add_parser("quit")
    a = ap.parse_args()

    if a.cmd == "launch":
        pid, _ = launch(a.project, a.port, a.data_dir)
        print(f"pid {pid} on port {a.port}")

    elif a.cmd == "quit":
        s = _state()
        if s.get("pid"):
            subprocess.run(["kill", str(s["pid"])])
            print(f"killed {s['pid']}")
        os.path.exists(STATE) and os.remove(STATE)

    elif a.cmd == "probe":
        tmp = tempfile.mkdtemp(prefix="fcprobe-")
        copy = os.path.join(tmp, os.path.basename(a.project))
        shutil.copy2(a.project, copy)
        pid, _ = launch(copy, a.port, os.path.join(tmp, "data"))
        print(f"copy:      {copy}\ndata-dir:  {tmp}/data\npid {pid} port {a.port}\n\n"
              "Drive the app (fcapp.py call ui.click ...), wait ~7s, then read:\n"
              f"  {tmp}/data/Recovery/*/snapshot.fcproj\n"
              "The real project was not touched.")

    elif a.cmd == "verify":
        if running():
            sys.exit("FilmCraft is already running — close it first so it cannot "
                     "overwrite the file you just wrote (pgrep -f FilmCraft)")
        sid, name = first_sequence(a.project)
        if sid is None:
            sys.exit("project has no sequence")
        data = a.data_dir or tempfile.mkdtemp(prefix="fcverify-")
        pid, _ = launch(a.project, a.port, data)
        log = os.path.join(data, "Logs", "filmcraft.log")
        bad = [l for l in open(log).read().splitlines()
               if any(w in l.lower() for w in ("error", "fail", "invalid", "missing"))] \
            if os.path.exists(log) else []
        call("ui.click", {"id": f"project.item.{sid}", "clicks": 2})
        time.sleep(4)
        els = call("ui.elements")
        clips = [e for e in els if e["id"].startswith("timeline.clip")]
        caps = any(e["id"].startswith("timeline.captionTrack") for e in els)
        shot = call("ui.screenshot", {"id": "panel.Program"})
        out = os.path.abspath("verify.png")
        shutil.copy(shot["path"], out)
        print(f"sequence {sid} {name!r}: {len(clips)} clips, captions={caps}")
        print(f"log errors: {len(bad)}" + ("".join("\n  " + b for b in bad[:5]) if bad else ""))
        print(f"screenshot: {out}  (read it — the Program monitor shows total duration "
              f"and whether captions render)")
        subprocess.run(["kill", str(pid)])
        os.path.exists(STATE) and os.remove(STATE)
        if bad or not clips:
            sys.exit(1)

    elif a.cmd == "call":
        print(json.dumps(call(a.method, json.loads(a.params) if a.params else {}),
                         ensure_ascii=False, indent=2))

    elif a.cmd == "elements":
        for e in call("ui.elements"):
            if not a.substr or a.substr in e["id"]:
                print(f"{e['id']:48} {e.get('label')}")

    elif a.cmd == "shot":
        r = call("ui.screenshot", {"id": a.id} if a.id else {})
        shutil.copy(r["path"], a.out)
        print(f"{a.out}  {r['width']}x{r['height']}")


if __name__ == "__main__":
    main()
