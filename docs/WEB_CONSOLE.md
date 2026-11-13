# USB console guide

Use a desktop browser over USB to view and change an ESP32-C3 that already runs compatible firmware. Home Assistant and Wi-Fi are not required.

[中文](./WEB_CONSOLE_CN.md)

This page describes only what the console does today. Software that runs, hardware that was exercised, and permission to publish are three different things. This guide is none of them.

## What you can do

1. Choose a radar and a board in desktop Chrome or Edge, and confirm the wiring.
2. Flash only after the release list has a compatible firmware and the page has checked its manifest. If no release is available, the guide still applies and the flash button stays off.
3. Close the installer, wait until the port is free, then connect USB debug yourself.
4. See whether the protocol is online, and read the model and observations the device reports.
5. Change one setting, validate it on the device, save it, and read it back.
6. Export a bounded observation log or a diagnostic summary.
7. Set up Home Assistant later, if you want it. That step is optional.

## What is supported

The first checked pair is **R60ABD1** with an **ESP32-C3 native USB port**. The page also lists other Completed 1D or 2D radars on ESP32-C3 whose UART is GPIO21/GPIO20. A listing is a catalog declaration, not MWCP acceptance for every pair.

Boards that share a name are not the same board. The ESP32-C3 Super Mini drawing is the repository reference layout. USB-serial bridges, other pins, and other chips are outside this promise. A YAML board name does not prove which board you are holding. Check the labels on the PCB.

The radar UART and the browser USB link are different wires:

- The computer plugs into the controller USB port. The browser opens only that link, at 115200 baud, 8 data bits, no parity, and 1 stop bit.
- The radar stays on the controller. GPIO21 is the controller TX and goes to the radar RX. GPIO20 is the controller RX and comes from the radar TX. That radar link is also 115200, 8 data bits, no parity, 1 stop bit, taken from the shared radar profile rather than guessed here.
- Do not wire the radar UART to the computer.
- Power and logic level come from the [getting started guide](../GETTING-STARTED.md), the [flasher maintenance notes](./FLASHER.md), and the module manual. The maintenance notes carry the R60ABD1 supply evidence. This guide does not add a voltage or current.

## Firmware: four separate facts

1. **The source contains the protocol.** The component tree includes mmwave_host. The R60ABD1 daily profile `tests/r60abd1-esp32c3.yaml` now includes `tests/common/r60abd1_mwcp.yaml` and enables it. The maintainer host profile is a separate firmware.
2. **A profile enables it at compile time.** A build of this R60 profile contains the USB console. The other models do not. A file in the repository does not mean the chip is already running it.
3. **An image was actually flashed.** Which file is on the board is known only from the flash record of that action. This guide does not invent an image identity, and it does not turn an older short test into new coverage.
4. **A version was published.** The page trusts the release index and a manifest that passes its checks. Official Alpha.3 has been published and deployed to Pages. The factory YAML uses `version: dev` as a source placeholder; the release workflow replaces it with the release version. It is not the identity of a published binary. A local candidate can be previewed on this computer; it is not an Alpha, a Beta, or a release page. A promoted Beta preserves the tested Alpha binary byte-for-byte without rebuilding, so the device reports the Alpha binary version while the distribution release channel is Beta.

Official Alpha.3 firmware has been published to [GitHub Releases](https://github.com/zomco/mmwave-component/releases/tag/v0.1.0-alpha.3) and deployed to [Pages](https://mmwave.owkor.com/). Select the corresponding version on the page to flash. Verified scope is R60ABD1 + native USB ESP32-C3 only. A flash button, or a source file, is not a published MWCP firmware. With no release, the page says there is no released firmware for this kit. That is not a successful flash. This R60 firmware does not use serial Improv, because that feature needs the same USB port. Use the fallback access point and captive portal when it is not on your Wi-Fi. BLE Improv, if present, is not the USB console. Wi-Fi scan is unavailable on this unpatched build.

## Opening the page

Use desktop Chrome or Edge. The address must be HTTPS, or localhost on your own machine. Firefox, Safari, and a phone can read the guide but cannot open a serial port. Close other serial tools that are holding the USB port, and use a data cable.

**USB debug** in the header scrolls to the console. **USB debug guide** under the console title opens this file on the repository's default branch. The production page does not say "simulation page". If you see simulation mode or replay mode, that screen is not a real device result.

## On your own device

These are user steps. They do not authorize anyone to flash or open a port now.

1. Open the page and choose **R60ABD1**.
2. Choose the board. The reference pair is **ESP32-C3 Super Mini**. Check the silkscreen, then tick the wiring confirmation.
3. Open the firmware step. When a compatible Beta exists, the page first says it is verifying the manifest. **Connect & flash** becomes available only after that check, and it uses that manifest. Alpha is never selected for you. To try an Alpha, select it yourself and tick the risk confirmation.
4. If the manifest is unavailable, the version does not match, or the checksum fails, flashing stays off. Do not substitute an unknown file.
5. Flashing happens in the browser installer. Close that window when it finishes, wait until the port is no longer reported busy, then connect manually. Closing the window does not release the port. If it still says busy, wait a few seconds and try again. The page does not take the port over, and closing the window does not mean the flash succeeded.
6. In **USB debug**, choose **Connect device**. In the system dialog, pick the controller USB port. Cancelling is not a device fault; choose **Connect device** again.
7. When the protocol is online, read configured_model, the dimension, and the firmware version. The model comes from the firmware configuration, not from the USB identifiers. If it differs from the page selection, the page uses the model the device reports. It does not change the flash target and it does not flash by itself.
8. Read a valid sample under **Quick check** or **Live data**. Unknown, stale, and historical samples are not "nobody present". A coordinate of 0, or an empty target list, is not presence either. Only a presence sample from the device counts.
9. **Vitals (not a medical device)** show a number only when the device declares that capability and the sample is valid. An undeclared capability shows no number. These figures are not for medical decisions.
10. Open **Configuration**. Change one field, choose **Validate on device**, read the change list, then choose **Save to device**. The complete success text is **Saved and read back**. Then choose **Disconnect**.

## What the five layers mean

- **Port**: whether the browser has the USB port open. Open is not a finished handshake.
- **Protocol**: whether the MWCP handshake finished. Online means this session is still alive.
- **Radar**: the link between the controller and the radar, as the device reports it. An online protocol does not replace it.
- **Data**: whether a usable observation is current. A historical sample is marked and is not the person in the room now.
- **Config**: whether configuration can be read or written. A failed read is not a successful save.

Presence follows the device: Unknown, Stale, Unsupported, Reported absent, or Reported present. Those words are not substitutes. Absent appears only when the device says so.

## How saving works

Edits stay in the memory of this browser tab. Validation and saving are two actions.

- With no edits, save stays off and the page says there are no unsaved changes.
- A save submits only the fields you changed.
- **Saved and read back** is complete success for that save.
- **The save is confirmed, but read-back failed** means the device accepted the write and the page has not read the result yet. Choose **Read from device**. That is not a finished check.
- **The read did not finish. This is not a save confirmation** is an ordinary read failure. Read again.
- If another client changed the device, the draft stays, save stays off, and you must **Read from device** first. The new values are there to compare. They do not replace the draft. After that read, decide whether to edit again and submit.
- **Save result unconfirmed** means this write has no clear outcome. The original operation may already be on the device. Stay on the page and choose **Query original save**, or disconnect, connect again, and query that same operation. Do not save again immediately, do not refresh to cancel it, and do not treat disconnect as cancel.
- Closing the browser drops that unconfirmed record from memory. This page does not promise that a refresh keeps the same operation available to query.
- **Stop tracking** only stops this page from asking. It does not mean the original write did not happen.

## Do not flash while debug holds the port

While USB debug is connecting, holding, or releasing the port, **Connect & flash** stays off. The notice says that closing the installer does not release the port. Choose **Disconnect**, wait until **Connect device** can be pressed again, then flash.

If closing the port fails, Disconnect remains and the page says the port is still held. Try Disconnect again. Do not treat the port as idle.

Do not connect debug while the installer window is open. After that window leaves the page, the page tells you to connect manually. It does not open the port for you.

## When something looks wrong

| What you see | What to do next |
| --- | --- |
| Port selection was cancelled | Choose **Connect device** again and pick the controller USB port. The radar is not broken. |
| Web Serial is unavailable, or the page is not a secure context | Use desktop Chrome or Edge over HTTPS or localhost. A phone can only read the guide. |
| The installer holds the port, or the port is being released | Close the installer and wait until the notice is gone. Do not keep clicking connect or flash. |
| Closing the port failed and it is still held | Choose **Disconnect** again. If it still fails, unplug USB, close other serial programs, and plug it back in. |
| No console protocol response | Check that the firmware includes MWCP, that you picked the controller USB port, and that the device has finished starting. This does not mean the radar hardware is damaged. The verified published combination is R60ABD1 with native USB ESP32-C3 on v0.1.0-alpha.3; check the release notes for other versions and models. |
| Session expired | Choose **Handshake again on this port**. The page does not reconnect by itself and does not write again while doing it. |
| Historical sample, or stale | Connect again before reading it. An old sample is not "nobody there now". |
| Another client changed the device | The draft is still there. **Read from device**, compare, then decide whether to submit. |
| Save result unconfirmed | **Query original save**, or query again after reconnecting. Do not save again and do not refresh. |
| Manifest check failed, or no release exists | Flashing stays off. Wait for a compatible published version. A button or an empty list is not a successful flash. |

## Recording and diagnostics

On **Live data**, choose **Start recording** to collect new observations. **Stop recording** keeps the samples available for **Export JSONL** or **Export CSV**. Clearing or starting a new recording asks for confirmation; canceling preserves the existing records. Disconnecting stops recording and keeps the records available for export. Closing or refreshing the page loses anything not exported. Only the latest 600 samples stay; older ones are dropped without automatically stopping recording.

Export removes values whose field names look like a password, token, or secret. A target index is not a stable identity of one person.

**Export diagnostic summary** on **Diagnostics** leaves out the SSID and IP unless you tick the option to include them. The password is still omitted. The summary has a bounded recent log, not the full conversation. The production page connects in hardware mode and does not label a simulation as a real device.

## Home Assistant comes later

USB verification does not need Home Assistant or Wi-Fi. A failed network setup does not block this console. Optional provisioning appears only when the device declares Wi-Fi. Without a declared scan, type the network name; the page will not change the firmware in order to scan. Sending the request does not mean the task finished.

To add Home Assistant and the room card afterwards, follow the [getting started guide](../GETTING-STARTED.md). The card repository is [mmwave-card](https://github.com/zomco/mmwave-card). This console does not include track fusion, a desktop timeline, or other advanced features.
