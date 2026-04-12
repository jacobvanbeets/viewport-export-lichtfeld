"""Viewport Export panel - export current view as JPG at configurable resolution."""

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import lichtfeld as lf

# Target heights – width is computed from the viewport's aspect ratio
RESOLUTIONS = [
    ("1080p", 1080),
    ("4K",    2160),
    ("8K",    4320),
]

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _save_jpg_dialog(default_name="viewport_export.jpg"):
    """Open a native save-file dialog for JPG files (Windows)."""
    if sys.platform != "win32":
        return None
    ps_script = f'''
    Add-Type -AssemblyName System.Windows.Forms
    $d = New-Object System.Windows.Forms.SaveFileDialog
    $d.Title = "Save Viewport as JPG"
    $d.Filter = "JPEG Image (*.jpg)|*.jpg"
    $d.FileName = "{default_name}"
    $d.DefaultExt = "jpg"
    if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
        Write-Output $d.FileName
    }}
    '''
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True,
            creationflags=_SUBPROCESS_FLAGS,
        )
        path = result.stdout.strip()
        return path if path else None
    except Exception:
        return None


class ViewportExportPanel(lf.ui.Panel):
    """Export current viewport as JPG at 1080p, 4K, or 8K."""

    id = "viewport_export.main_panel"
    label = "Viewport Export"
    space = lf.ui.PanelSpace.MAIN_PANEL_TAB
    order = 60
    update_interval_ms = 500

    def __init__(self):
        self._resolution_idx = 0
        self._quality = 95
        self._status = ""
        self._status_color = (1.0, 1.0, 1.0, 1.0)

    def draw(self, ui):
        scale = ui.get_dpi_scale()

        # --- Resolution ---
        ui.label("Resolution:")
        labels = [r[0] for r in RESOLUTIONS]
        changed, new_idx = ui.combo("##vp_resolution", self._resolution_idx, labels)
        if changed:
            self._resolution_idx = new_idx

        _, target_h = RESOLUTIONS[self._resolution_idx]
        ui.text_disabled(f"Height: {target_h} px (width from viewport aspect ratio)")

        ui.spacing()

        # --- JPG Quality ---
        ui.label("JPG Quality:")
        changed, val = ui.slider_int("##vp_quality", self._quality, 1, 100)
        if changed:
            self._quality = val

        ui.spacing()
        ui.separator()
        ui.spacing()

        # --- Export button ---
        if ui.button_styled("Export JPG", "primary", (-1, 32 * scale)):
            self._do_export()

        # --- Status ---
        if self._status:
            ui.spacing()
            ui.text_colored(self._status, self._status_color)

    # ------------------------------------------------------------------

    def _do_export(self):
        # Open save dialog first so we don't render if user cancels
        path = _save_jpg_dialog()
        if not path:
            return
        if not path.lower().endswith(".jpg"):
            path += ".jpg"

        _, target_h = RESOLUTIONS[self._resolution_idx]
        self._set_status("Capturing viewport...", warning=True)

        try:
            # capture_viewport() grabs exactly what the viewer shows
            vp = lf.capture_viewport()
            if vp is None or vp.image is None:
                self._set_status("No viewport to capture.", error=True)
                return

            arr = np.asarray(vp.image.cpu().contiguous())

            # OpenGL framebuffer is bottom-up; flip to standard top-down
            arr = np.flip(arr, axis=0).copy()

            arr = (arr * 255.0).clip(0, 255).astype(np.uint8)
            img = Image.fromarray(arr, "RGB")

            # Scale to target height, preserving the viewport aspect ratio
            src_w, src_h = img.size
            target_w = max(1, round(src_w * target_h / src_h))
            if (src_w, src_h) != (target_w, target_h):
                img = img.resize((target_w, target_h), Image.LANCZOS)

            img.save(path, "JPEG", quality=self._quality)

            self._set_status(f"Saved: {Path(path).name}", success=True)

        except Exception as e:
            self._set_status(f"Error: {e}", error=True)

    # ------------------------------------------------------------------

    def _set_status(self, msg, *, success=False, warning=False, error=False):
        self._status = msg
        if success:
            self._status_color = (0.2, 1.0, 0.2, 1.0)
        elif warning:
            self._status_color = (1.0, 0.8, 0.2, 1.0)
        elif error:
            self._status_color = (1.0, 0.3, 0.3, 1.0)
        else:
            self._status_color = (1.0, 1.0, 1.0, 1.0)
