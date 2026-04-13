# Viewport Export – LichtFeld Studio Plugin

Export the current viewport as a **JPG** or **PNG** image with optional **RGBA transparency** via BW2A alpha extraction.

## Features

- Captures exactly what you see in the viewer
- **Format support**: JPG (adjustable quality) and PNG (adjustable compression)
- **Resolution presets**: Viewport (native), 1080p, 4K, 8K — height-based, preserves viewport aspect ratio
- **RGBA transparency**: PNG export with BW2A (Black/White to Alpha) — automatically captures against black and white backgrounds to recover a clean alpha channel
- Version-aware Y-axis handling (LichtFeld ≥ 0.5.1)

## Installation

### Via Plugin Manager (recommended)

1. Open LichtFeld Studio
2. Go to **Tools → Plugin Manager**
3. Search for **Viewport Export**
4. Click **Install**

### Manual

Clone this repository into your LichtFeld Studio plugins directory:

```
git clone https://github.com/jacobvanbeets/viewport-export-lichtfeld.git "%USERPROFILE%\.lichtfeld\plugins\viewport_export"
```

Restart LichtFeld Studio. Dependencies (Pillow, numpy) are installed automatically.

## Usage

1. Open the **Viewport Export** tab in the right-side panel
2. Choose a resolution and format (JPG or PNG)
3. For PNG, optionally enable **Transparency (RGBA)** for BW2A alpha extraction
4. Click **Export** and pick a save location

## Credits

Thanks to [bb6](https://github.com/bgofish) for code contributions.
