# Getting Started — From Parts to a Working Room Map

[中文文档](./GETTING-STARTED_CN.md)

This is the complete first-time setup, start to finish. It assumes no prior
ESPHome knowledge and no soldering beyond four wires.

At the end you will have a radar that reports **where a person is standing in
your room**, in centimetres from a corner you choose, visible live on a Home
Assistant dashboard.

Budget about 45 minutes. Most of it is waiting for Home Assistant to restart.

---

## What you need

| Item | Notes |
| --- | --- |
| An ESP32-C3 board | The only chip family currently built. ESP32-S3 is planned. |
| A supported radar module | See the [model table](./README.md#radar-model-status). LD2450 is the easiest starting point. |
| 4 jumper wires | Female-to-female is usually right for both boards. |
| A USB-C cable | Must be a **data** cable. Charge-only cables are the single most common reason flashing fails. |
| Home Assistant | Any install type, with [HACS](https://hacs.xyz/) already set up. |
| Chrome or Edge | Required for browser flashing. Firefox and Safari do not support Web Serial. |

You do **not** need: a soldering iron, the ESPHome add-on, Python, or a GitHub
account.

---

## Step 1 — Wire the radar to the ESP32-C3

Four wires. The two data wires **cross over** — the radar's TX goes to the
ESP32's RX, and vice versa. Getting these backwards is the second most common
failure, and it fails silently: the device boots fine and simply never reports
a target.

| ESP32-C3 pin | Radar pin | Purpose |
| --- | --- | --- |
| `5V` or `3.3V` | `VCC` | Power — **check your radar's datasheet**, some are 5 V and some are 3.3 V |
| `GND` | `GND` | Ground |
| `GPIO21` | `RX` | ESP32 transmits → radar receives |
| `GPIO20` | `TX` | ESP32 receives ← radar transmits |

> **LD2410 is the exception:** it uses `GPIO4` (TX) and `GPIO5` (RX) instead.
> Every other supported model uses GPIO21/GPIO20 as above.

Feeding 5 V into a 3.3 V-only module destroys it. If the datasheet is
ambiguous, 3.3 V is the safe choice — a module that wants 5 V will simply fail
to respond rather than burn out.

---

## Step 2 — Flash the firmware from your browser

No software to install. The web flasher talks to the board over USB directly.

1. Plug the ESP32-C3 into your computer.
2. Open the **[Web Flasher](https://zomco.github.io/mmwave-component/)** in
   Chrome or Edge.
3. Pick your radar model from the list.
4. Click **Connect**, choose the serial port in the browser dialog, and click
   **Install**.
5. When flashing finishes, the page offers **Wi-Fi provisioning** — enter your
   network name and password there.

The device joins your Wi-Fi and announces itself. If the port list is empty,
see [Troubleshooting](#troubleshooting).

---

## Step 3 — Adopt the device in Home Assistant

Home Assistant discovers the device on its own.

1. Go to **Settings → Devices & Services**.
2. A card reading **ESPHome — Discovered** should appear within a minute or
   two. Click **Configure**, then **Submit**.
3. The device is added with its entities: presence, target coordinates, and a
   set of calibration controls.

Note the device name shown here (something like `ld2450-a4c1f8`). You will
need its entity IDs in Step 5.

If nothing is discovered, add it manually: **Add Integration → ESPHome**, then
enter the device's IP address from your router's client list.

---

## Step 4 — Install the dashboard card

The card is what turns numbers into a picture of your room.

1. In HACS, open **Frontend**.
2. Search for **MMWave Radar Card**, or add
   `https://github.com/zomco/mmwave-card` as a custom repository under
   category **Lovelace**.
3. Install it, then **restart Home Assistant**.

[![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin)

---

## Step 5 — Add the card to a dashboard

1. Open any dashboard, click the pencil icon, then **Add Card**.
2. Search for **MMWave Radar Card**.
3. Choose your radar model from the drop-down.
4. The editor then shows one picker per entity the model needs, filtered to
   plausible candidates. Fill in the required ones.

No YAML required. If you prefer YAML anyway, see the
[card's DIY guide](https://github.com/zomco/mmwave-card/blob/main/DIY.md).

---

## Step 6 — Calibrate

This is the step that makes the difference between raw radar output and real
room coordinates, and it is the one people skip. Ten minutes here saves hours
of debugging automations that fire from the wrong room.

The card has three tabs, meant to be done in order.

### Tab ① — Geometry & boundary

Tell the card where the radar physically is.

Pick one corner of the room as the origin. Measure, in centimetres:

- **`radar_x`** — how far along the wall from that corner
- **`radar_y`** — how far out from that wall
- **`radar_z`** — height above the floor

Then drag the room boundary polygon to match your floor plan. Anything outside
this polygon gets rejected — this is what stops the radar seeing your
neighbour through the wall.

Measure to the radar module itself, not the ESP32 board. ±5 cm is good enough.

### Tab ② — Yaw calibration

Tell the card which way the radar is pointing.

Stand at a known spot, mark it on the plan, then stand at a second spot at
least a couple of metres away and mark that. The card solves for the heading
from the two readings.

`yaw = 0` means the radar faces along room **+Y**. Positive yaw turns
clockwise seen from above.

### Tab ③ — Live view

Walk around and watch the dot. If it tracks you, you are done.

If the dot moves **mirrored** — you walk left, it goes right — your yaw is
180° out. If it moves at right angles to you, it is 90° out. Go back to Tab ②
rather than nudging the number by hand.

Press **Save**, which writes the calibration to the device so it survives a
reboot.

---

## Optional — More than one radar

One radar per room needs nothing further; you are finished.

Covering a large or L-shaped space with several radars, and wanting one fused
picture with stored history, additionally needs the
**[mmwave-fusion](https://github.com/zomco/mmwave-fusion)** integration — a
separate HACS entry under the **integration** category.

Without it the card still draws a fused view, but the fusion happens in your
browser and nothing is stored. The card says so plainly rather than pretending
otherwise.

Fusion needs models that report 2-D position. Range-only models (LD2410 family,
LD2411, LD2412, LD2420, LD2450A, LD6002, RD03E) report distance without
direction, so they cannot be fused and the editor does not offer them.

---

## Troubleshooting

### The flasher shows no serial ports

Almost always the cable. Try a different USB-C cable known to carry data.

Failing that, some boards need `BOOT` held down while you plug them in.
Windows occasionally needs a USB-serial driver — CP210x or CH340 depending on
the board.

### Flashed fine, but no entities appear in Home Assistant

The device is probably not on Wi-Fi. It falls back to its own access point
named after the model with `Fallback` appended. Connect to that from a phone
and re-enter the network details.

### Presence works, but coordinates are always 0 or blank

The TX/RX wires are crossed the wrong way, or the module is underpowered.
Re-check the table in Step 1. A module browning out under a weak 3.3 V supply
reports presence but no position.

### Coordinates jump wildly, or someone is detected in an empty room

mmWave passes through plasterboard and glass. Draw the boundary polygon in
Tab ① tightly around the actual room — out-of-bounds targets stop driving
presence once you do.

Large metal surfaces, mirrors and moving fans all produce reflections that
look like people. Moving the radar half a metre often fixes what no amount of
configuration will.

### The dot is mirrored or rotated

Yaw is wrong. Redo Tab ②. See the note in Step 6.

---

## Where to go next

| You want to | Read |
| --- | --- |
| Write your own ESPHome YAML, change pins, add sensors | [DIY.md](./DIY.md) |
| Understand the coordinate transform and boundary filter | [DIY.md — Features](./DIY.md#features) |
| Configure the card in YAML | [card DIY guide](https://github.com/zomco/mmwave-card/blob/main/DIY.md) |
| Look up one model's entities | `docs/<model>/README.md` |
| Set up multi-radar fusion | [mmwave-fusion](https://github.com/zomco/mmwave-fusion) |
