---
name: draw-esp-svg
description: Creates a 1:1 SVG representation of an ESP/Core board for the wiring diagram based on user-provided dimension and pinout images.
---

# Draw ESP Core Board SVG Skill

When the user provides an image or dimensions of a new ESP/Core board (e.g., ESP32-C3 Supermini, ESP8266, ESP32-S3) and asks you to draw it, follow this strict procedure to add it to the wiring diagram in `static/index.html`.

## 1. Analyze the Physical Dimensions and Pinout
- **Scale:** The standard rendering scale is `1mm = 8px`. 
- **Dimensions:** Understand the physical width and height (in mm) of the board to establish the SVG bounds.
- **Pin Locations:** Identify the physical coordinates of the pins that need to be mapped (usually 5V/3V3, GND, TX, RX). Calculate their relative millimeter positions from the top-left edges. Note that ESP board pins are usually arranged in two parallel rows along the left and right edges (e.g., 2.54mm pitch).
- **Pin Mapping:** Identify which physical pins serve the purpose of `VCC (5V/3V3)`, `GND`, `TX`, and `RX`.

## 2. Update `ESP_CONFIG` (or equivalent structure)
Add the new ESP board model configuration to `static/index.html` (inside the `chipFamily` configuration section).
- Define `width` and `height` (in mm).
- Define the `pins` array. For each mapped pin:
  - `name`: Silkscreen label on the ESP board (e.g., '5V', 'GND', 'TX', 'RX').
  - `x`, `y`: Coordinates in millimeters (relative to the top-left of the board).
  - `type`: Standard internal type for wire matching (`vcc`, `gnd`, `tx`, `rx`).
  - `color`: The specific color code used for wiring (e.g., `#ef4444` for VCC, `#22c55e` for TX, etc.).

## 3. Draw the SVG Layout
In the rendering block for the ESP board in `index.html`, create the 1:1 pixel-perfect SVG:
- **Base PCB:** Draw the main `<rect>` with the scaled dimensions (`width * 8`, `height * 8`). Use standard PCB colors like black `#1e293b`, dark blue `#1e40af`, or purple.
- **USB Port:** Draw the USB-C or Micro-USB port, typically positioned at the top edge or bottom edge. Use metallic colors like `#cbd5e1` and `#94a3b8` to give it a 3D feel.
- **Main Chip & Shield:** Draw the ESP metallic RF shield (silver `#94a3b8` with `#f1f5f9` highlights) or the raw black MCU chip in the center.
- **Antenna:** Draw the PCB Wi-Fi antenna trace (usually a meandering or zig-zag gold/copper trace at the top of the board).
- **Buttons & LEDs:** Add the BOOT and RESET buttons (small black/silver squares) and any onboard LEDs.
- **Unmapped Pins:** The core board has many pins (GPIOs, EN, etc.) that are not used for the radar wiring. You must manually draw the gold pads (using `<circle r="4" fill="#fbbf24">`) and their silkscreen labels for all unmapped pins so the board looks complete and realistic.

## 4. Wiring Algorithm Integration
- **Pin Halos & Routing:** The global `espPinsRender` will automatically draw the mapped pins, highlight them with a colored halo (`stroke={pin.color}`), print their labels, and act as the starting point for the wiring algorithm.
- **Routing Direction:** The wires will automatically route to the left if the pin is on the left half of the board (`x < width/2`), and to the right if it's on the right half.
- Ensure your ESP pin `x` and `y` coordinates perfectly align with the physical pitch (20px per 2.54mm) so the visual alignment is flawless.

## 5. Execution
Always use the `multi_replace_file_content` tool to patch `static/index.html`. This ensures you cleanly inject the SVG `<g>` block without disrupting the complex orthogonal wiring logic.
