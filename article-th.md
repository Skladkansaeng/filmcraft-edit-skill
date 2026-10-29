# ให้ Claude ตัดต่อวิดีโอให้: สร้าง skill คุม FilmCraft จาก screen recording 19 นาที เหลือ 3 นาทีครึ่ง

> เคสจริง: ผมมี screen recording 4 ไฟล์ รวม 18 นาที 53 วินาที ไม่มีเสียงสักไฟล์ ต้องทำเป็นวิดีโอสอนใช้งานระบบ
> จบที่ 3:30 พร้อมคำบรรยายไทย โดยไม่ต้องลากไทม์ไลน์เองสักครั้ง

---

## ปัญหา

งานคือทำวิดีโอสอนใช้ **Content Seed Builder** ของระบบ EdET — ตั้งแต่เตรียมข้อมูลในสเปรดชีต ไปจนถึงกด seed ลง MongoDB และต้องแยกวิธีตาม skill (Reading / Writing / Listening / Speaking)

ของที่มีคือ screen recording ดิบ 4 ไฟล์:

| ไฟล์ | ความยาว | หมายเหตุ |
|---|---|---|
| 09.46.52.mov | 5:49 | โครงสร้างสเปรดชีต + Parse Content |
| 09.53.53.mov | 4:30 | สลับ Skill เป็น Writing MCQ |
| 10.00.17.mov | 6:53 | n8n อัปโหลดเสียงขึ้น GCS |
| 11.38.49.mov | 1:41 | Step 2 Split to Seed |

ทั้งหมด 2880×1800 @60fps, H.264 และ `audio_streams: []` — **ไม่มีเสียงเลยสักไฟล์** แปลว่าจะตัดตามจังหวะพูดไม่ได้ ต้องใช้คำบรรยายกำกับแทน

ปัญหาถัดมาคือ FilmCraft **ไม่มี API สำหรับตัดต่อ** มีแค่ไฟล์โปรเจกต์ `.fcproj` ที่เป็น JSON

## แนวคิด: เขียนไทม์ไลน์ลงไฟล์ตรงๆ แล้วพิสูจน์ว่ามันเปิดได้

ถ้าไฟล์โปรเจกต์เป็น JSON ก็เขียนมันตรงๆ สิ — ฟังดูง่าย แต่มีกับดักอยู่ว่า **ถ้าเดา field ผิด ไฟล์จะเปิดไม่ขึ้น** และคุณจะไม่รู้จนกว่าจะลองเปิด

ทางออกคือหาคำตอบจากตัวแอปเอง FilmCraft มี flag ที่ไม่ได้โฆษณาไว้:

```
--control <port>   start the localhost JSON-lines control server
                   (requires FILMCRAFT_CONTROL_TOKEN, 64 random hex characters)
```

เป็น UI automation server พูด JSON บรรทัดละ message มี `ui.elements`, `ui.click`, `ui.drag`, `ui.screenshot` และอีกชุดหนึ่ง พอบวกกับ preference ที่ตั้ง `recoveryJournal: true, recoveryIntervalSeconds: 5` ก็ได้ลูปเรียนรู้ที่เชื่อถือได้:

1. ก๊อปโปรเจกต์ไปที่ scratch (ห้ามแตะไฟล์จริง)
2. เปิดด้วย `--control` และ `--data-dir` แยก
3. สั่งแอปทำสิ่งที่อยากรู้ เช่น `ui.drag` ลากคลิปลงไทม์ไลน์
4. รอ 7 วินาที อ่าน `<data-dir>/Recovery/*/snapshot.fcproj`

snapshot คือโปรเจกต์เต็มรูปแบบที่แอปเขียนเอง — ได้ schema จริงทุก field ไม่ต้องเดา

> เกร็ด: ผมลองแกะชื่อ field จาก binary ก่อน (เป็น Rust + serde) แต่ `FIELDS` array ของ serde โดน LTO ตัดทิ้ง เพราะ `serde_json` ไม่ได้ใช้ตอน deserialize เหลือแต่ชื่อ field ที่ต่อกันเป็นก้อนเดียว เรียงลำดับเดาได้แต่ไม่ 100% — สู้ให้แอปพ่นคำตอบออกมาเองไม่ได้

เมื่อรู้ schema แล้ว งานที่เหลือก็แค่แพ็กเป็น skill

---

## ติดตั้ง

```bash
git clone <repo> ~/src/filmcraft-edit-skill
ln -s ~/src/filmcraft-edit-skill/.claude/skills/filmcraft-edit ~/.claude/skills/filmcraft-edit
```

ต้องมี FilmCraft 0.14.x (`schema_version: 15`), Python 3 และ ffmpeg

---

## ใช้งานจริง 5 ขั้น

### 1. ดูว่ามีอะไรอยู่ในมือ

```bash
S=.claude/skills/filmcraft-edit/scripts
python3 $S/fcproj.py media Untitled.fcproj
```

```
  1   101.125s (1:41.125)  2880x1800@60  audio=0  Screen Recording ... 11.38.49.mov
  2   413.213s (6:53.213)  2880x1800@60  audio=0  Screen Recording ... 10.00.17.mov
  3   269.853s (4:29.853)  2880x1800@60  audio=0  Screen Recording ... 09.53.53.mov
  4   349.285s (5:49.285)  2880x1800@60  audio=0  Screen Recording ... 09.46.52.mov
```

เลข `1`–`4` คือ **item id** ที่จะใช้อ้างใน plan และ `audio=0` บอกตั้งแต่ต้นว่าอย่าไปสัญญาเรื่องเสียง

### 2. หาจุดตัดด้วย ffmpeg ไม่ใช่ด้วยการเดา

19 นาทีไล่ดูเองก็เสียเวลา ใช้สองท่านี้แทน

**จับจุดเปลี่ยนฉาก:**

```bash
ffmpeg -hwaccel videotoolbox -i clip.mov \
  -vf "scale=480:-1,select='gt(scene,0.25)',metadata=print:file=scenes.txt" -an -f null -
```

ได้ไทม์สแตมป์ออกมาเป็นชุด เช่น `8.7 39.3 44.0 65.1 75.2 ... 325.4` ซึ่งคือขอบของแต่ละช่วง

**ดูว่าแต่ละช่วงคือเนื้อหาอะไร** — ครอปเฉพาะแถบหัวข้อแล้วต่อกันเป็นแผ่นเดียว อ่านทีละ 8 ช่วงในภาพเดียว:

```bash
for t in 10 41 46 67 71 77 83 93; do
  ffmpeg -ss $t -i clip.mov -frames:v 1 \
    -vf "crop=2880:380:0:300,scale=1400:-1" -y "s_$t.png"
done
ffmpeg -i "s_%d.png" -vf "tile=1x8" -y map.png
```

ท่านี้สำคัญกว่าที่คิด — screen recording แต่ละเฟรมหน้าตาคล้ายกันหมด การครอปเฉพาะแถบที่บอก "ตอนนี้อยู่หน้าไหน / เลือก Skill อะไร" ทำให้ map ทั้งคลิปได้ในภาพไม่กี่ภาพ

### 3. เขียน edit plan

นี่คือหัวใจ — ทั้งงานตัดต่ออยู่ในไฟล์ JSON ไฟล์เดียว

```json
{
  "project": "/Users/me/Documents/Untitled.fcproj",
  "sequence_name": "EdET Content Builder — How To",
  "fps": 60,
  "caption_language": "th",
  "sections": [
    {
      "name": "1 - Prep: sheet format",
      "label": "Caribbean",
      "speed": 3.0,
      "segments": [{ "item": 4, "in": 44.0, "out": 80.0 }],
      "captions": ["ขั้นที่ 1 · เตรียมข้อมูลใน sheet ให้ตรง format"]
    },
    {
      "name": "4a - Step 1 Parse Content: Reading",
      "label": "Violet",
      "speed": 2.0,
      "segments": [
        { "item": 4, "in": 193.4, "out": 215.0 },
        { "item": 4, "in": 260.0, "out": 280.0 },
        { "item": 3, "in": 0.5,   "out": 19.2 }
      ],
      "captions": [
        "ขั้นที่ 4 · Step 1 Parse Content — Skill: Reading",
        "เลือกไฟล์ .xlsx → เลือก Sheet = Reading → Skill = Reading แล้วตรวจ Preview"
      ]
    }
  ]
}
```

สิ่งที่ไม่ต้องเขียนเอง:

- **ตำแหน่งบนไทม์ไลน์** — คลิปต่อกันตามลำดับ คำนวณให้
- **หน่วยเวลา** — `in`/`out` เป็นวินาทีในไฟล์ต้นฉบับ ส่วนข้างในเป็น tick (1 วินาที = 254,016,000,000 tick) แปลงให้
- **marker** — ทุก section ได้หมุดที่เฟรมแรกอัตโนมัติ
- **ตำแหน่งคำบรรยาย** — กระจายเท่าๆ กันในช่วงนั้น เขียน 1 บรรทัด = คลุมทั้ง section

`label` คือสีของคลิป (Violet, Caribbean, Mango, Purple, Green, …) ทำให้มองไทม์ไลน์แล้วเห็นโครงเรื่องทันที

แล้วสั่ง:

```bash
python3 $S/fcproj.py apply plan.json
```

```
backup: /Users/me/Documents/Untitled.fcproj.bak
Untitled.fcproj: sequence 11 "EdET Content Builder — How To" 3:30.72  (6 sections)
```

มันสำรองไฟล์ให้ก่อน และตรวจทุก segment กับความยาวสื่อจริง ถ้าเกินจะไม่เขียนไฟล์:

```
section 'bad': segment 1 runs past the media (12000 > 6067 frames)
```

### 4. พิสูจน์ว่าเปิดได้จริง

ขั้นนี้ห้ามข้าม ไฟล์ที่ "ดูถูก" กับไฟล์ที่ "เปิดขึ้น" เป็นคนละเรื่อง

```bash
python3 $S/fcapp.py verify Untitled.fcproj
```

```
sequence 11 'EdET Content Builder — How To': 10 clips, captions=True
log errors: 0
screenshot: verify.png
```

มันเปิด FilmCraft จริงแบบแยก data-dir, เปิด sequence, นับคลิป, grep log หา error และถ่ายภาพ Program monitor มาให้ — ภาพนั้นบอกความยาวรวมและบอกว่าคำบรรยายขึ้นจริงไหม ถ้ามี FilmCraft เปิดค้างอยู่มันจะปฏิเสธการทำงาน เพราะแอปถือโปรเจกต์ไว้ในหน่วยความจำและจะ save ทับทีหลัง

### 5. แก้รอบถัดไป: dump → แก้ plan → apply

ตรงนี้คือข้อดีที่สุดของการเก็บงานเป็น plan ตอนลูกค้า (ก็คือตัวผมเอง) ขอแก้

> "ช่วง prepare ทำเป็น speedup"

```bash
python3 $S/fcproj.py dump Untitled.fcproj > plan.json
# แก้ "speed": 1.0 -> 2.0 ใน 3 section แรก
python3 $S/fcproj.py apply plan.json
```
6:24 → 5:08

> "ขอ speed เร็วกว่านี้หน่อย"

แก้ `2.0` เป็น `3.0` → 4:42

> "ขั้นตอนที่ 4 parse content ให้แยกตาม skill และใช้ style x2"

แยก section `4` กับ `5` เป็น `4a` / `4b` ตั้ง speed `2.0` ทั้งคู่ → **3:30**

`dump` กับ `apply` round-trip ตรงกันเป๊ะทุกค่า จุดสำคัญคือ **มันคำนวณจากความยาวต้นฉบับเสมอ** ไม่ใช่จากคลิปที่เร่งไปแล้ว — ถ้าไปแก้ tick ในไฟล์โปรเจกต์เองตรงๆ คุณจะได้ความเร็วซ้อนกันโดยไม่รู้ตัว

---

## กับดักที่เจอจริง (และเสียเวลาไปแล้ว)

**ภาษาไทยขึ้นในวิดีโอ แต่ไม่ขึ้นใน UI ของแอป**
คลิปชื่อภาษาไทยบนไทม์ไลน์กลายเป็นกล่องว่าง ▯▯▯ แต่คำบรรยายที่เรนเดอร์ลงภาพขึ้นสวยงาม เป็นข้อจำกัดฟอนต์ของ UI ไม่ใช่ปัญหา encoding **อย่าไปแก้ด้วยการ re-encode** — เก็บไทยไว้ใน `captions` และให้ `name` เป็น ASCII

**เฟรมต้องลงตัว**
ที่ 60fps คลิป 36.0 วินาที = 2160 เฟรม เร่ง 2x กับ 3x ลงตัว แต่ 4x ไม่ (2658 ÷ 4 = 664.5) เลือก speed ที่หารลงตัว ไม่งั้นจะเสียเศษเฟรมทุกคลิป

**สูตร speed ต้องตรงกันสามที่**

```
duration = (จำนวนเฟรมต้นฉบับ / k) เฟรม
speed    = k
effects[time_remap].params.speed.value.Float = k * 100
```

**screen recording เป็น VFR**
ความยาวสื่อมักไม่ลงตัวเป็นเฟรมพอดี (คลิปหนึ่งของผมคือ 6067.5 เฟรม) อย่าตัดชิดเฟรมสุดท้าย

**ปิดแอปก่อนเขียนไฟล์** ไม่งั้น Cmd+S ทีหลังทับงานคุณหมด

---

## ผลลัพธ์

| | |
|---|---|
| ต้นฉบับ | 4 ไฟล์ รวม 18:53 |
| ผลลัพธ์ | 3:30.72 — 10 คลิป, 6 marker, 11 คำบรรยาย |
| แยกเป็น | 3 ช่วงเตรียมข้อมูล (3x), 2 ช่วง Parse Content แยกตาม skill (2x), 1 ช่วง Split to Seed (ปกติ) |

ที่น่าสนใจกว่าตัวเลขคือ **รอบการแก้** การขอ "เร็วกว่านี้" หรือ "แยกตาม skill" กลายเป็นแก้ JSON ฟิลด์เดียวแล้วสั่ง apply ใหม่ ไม่ใช่การลากไทม์ไลน์ใหม่ทั้งเส้น

## ข้อจำกัด

ตัดแบบ cut ล้วนเท่านั้น — `Transition`, graphic/title และ `SequenceView` **ยังไม่ได้ยืนยัน schema** เครื่องมือจึงปฏิเสธที่จะเดา field พวกนี้ ซึ่งผมคิดว่าถูกแล้ว: เครื่องมือที่ยอมรับว่าตัวเองไม่รู้อะไร ดีกว่าเครื่องมือที่เดาแล้วทำไฟล์พัง

ถ้าอยากต่อยอด มี `fcapp.py probe` ที่ก๊อปโปรเจกต์ เปิดแบบแยก แล้วชี้ไปที่ recovery snapshot ให้ — ใช้ลูปเดิมที่เล่าไว้ตอนต้นได้เลย

---

**Repo:** `filmcraft-edit` — skill, สคริปต์ และเอกสาร schema กับ control protocol ทั้งหมด

เขียนร่วมกับ Claude Code
