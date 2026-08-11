---
name: draw-radar-svg
description: Creates a 1:1 SVG representation of a radar module for the wiring diagram based on user-provided dimension and pinout images.
---

# Draw Radar SVG Skill

When the user provides an image or dimensions of a new radar module and asks you to draw it, follow this strict procedure to add it to the wiring diagram in `static/index.html`.

## 1. Analyze the Physical Dimensions and Pinout
- **Scale:** The standard rendering scale is `1mm = 8px`. 
- **Dimensions:** Understand the physical width and height (in mm) of the board to establish the bounds.
- **Pin Locations:** Identify the physical coordinates of the UART/Power pins used for flashing (usually VCC/3V3, GND, TX, RX). Calculate their relative millimeter positions from the top-left edges.
- **Pin Types:** Map the pins to the standard internal types: `vcc`, `gnd`, `tx`, `rx`, `other`. Cross-reference schematic tables to ensure correct mapping. 

## 2. Update `RADAR_CONFIG`
Add the new radar model to the `RADAR_CONFIG` object in `static/index.html`.
- Define `width` and `height` (in mm).
- Define the `pins` array. For each pin:
  - `name`: Silkscreen label (e.g., '3V3', 'GND', 'TX', 'RX').
  - `x`, `y`: Coordinates in millimeters (relative to the top-left of the radar).
  - `type`: Standard type for wire routing matching.
  - Optional Overrides: Use `labelDx`, `labelDy`, `anchor`, and `fontSize` if the default left/right text positioning overlaps with other elements or if pins are closely packed on the top/bottom edges.

## 3. Update `getRadarType()`
Add a string matching condition in the `getRadarType` function so the frontend correctly selects the new radar based on the firmware ID string (e.g., `if (s.includes('new_radar')) return 'new_radar';`).

## 4. Draw the SVG Layout
In the rendering block of `index.html` (inside the `radarType === '...'` conditional), create the 1:1 pixel-perfect SVG:
- **Base PCB:** Draw the main `<rect>` with the correct scaled dimensions (`width * 8`, `height * 8`) and background color (e.g., green `#166534`, blue `#1e40af`, or gold `#eab308`/black `#020617`).
- **Antenna Traces:** Use `<rect>`, `<path>`, and `<circle>` to meticulously recreate the microstrip antenna arrays, feed lines, and impedance matching structures. Rely on high-contrast colors like `#eab308` or `#fbbf24` for gold traces, or light yellow `#fde68a` for exposed substrates.
- **Chips & Silkscreen:** Draw the main MCU (usually a dark square like `#1e293b`), along with its pins and any distinctive silkscreen text, logos, or dotted keepout borders using `#cbd5e1`.
- **Passive Components & Vias:** Add small rectangles and circles for capacitors, resistors, test pads, and vias to give the module a realistic industrial feel.
- **Unmapped Pins:** If there are physical pins (like OT1/OT2) that are not part of the main flashing pins, draw them manually using `<circle r="4" fill="#fbbf24">` and `<text>` labels to preserve the hardware's look.

## 5. Wiring Algorithm Considerations
- The global `radarPinsRender` will automatically draw the mapped pins, their glowing halos, their text labels, and route the orthogonal wires.
- **Routing Direction:** The wires will automatically route to the left if the pin is on the left half of the board (`x < width/2`), and to the right if it's on the right half. Ensure your pin `x` coordinates are accurate so the automatic routing elegantly splits and avoids overlapping the center of the board.

## 6. Execution
Always use the `multi_replace_file_content` tool to patch `static/index.html`. This ensures you cleanly update the configuration arrays and inject the SVG `<g>` block without breaking existing modules.
