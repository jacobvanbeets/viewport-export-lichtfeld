# Viewport Export – LichtFeld Studio Plugin

Export the current viewport as a JPG image at **1080p**, **4K**, or **8K** resolution.

## Features

- Captures exactly what you see in the viewer
- Resolution presets: 1080p, 4K, 8K (height-based, preserves viewport aspect ratio)
- Adjustable JPG quality (1–100)

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
2. Choose a resolution and JPG quality
3. Click **Export JPG** and pick a save location
