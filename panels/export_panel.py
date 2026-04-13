"""Viewport Export panel — JPG/PNG export with optional BW2A alpha extraction."""

import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import lichtfeld as lf

# ── Version detection ─────────────────────────────────────────────────────────
def _parse_version(v: str) -> tuple:
    parts = v.lstrip("v").split(".")[:3]
    return tuple(int(re.match(r"\d+", x).group()) for x in parts)

Y_UP = _parse_version(lf.__version__) >= (0, 5, 1)

RESOLUTIONS = [
    ("Viewport", None),
    ("1080p",    1080),
    ("4K",       2160),
    ("8K",       4320),
]
FORMATS = ["JPG", "PNG"]
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_dialog(default_name, title, file_filter, ext):
    if sys.platform != "win32":
        return None
    ps_script = f'''
    Add-Type -AssemblyName System.Windows.Forms
    $d = New-Object System.Windows.Forms.SaveFileDialog
    $d.Title = "{title}"
    $d.Filter = "{file_filter}"
    $d.FileName = "{default_name}"
    $d.DefaultExt = "{ext}"
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


def _default_path(filename):
    return str(Path(os.getcwd()) / filename)


def _capture_arr():
    """Capture the current viewport; returns float32 (H,W,3) array or None."""
    vp = lf.capture_viewport()
    if vp is None or vp.image is None:
        return None
    arr = np.asarray(vp.image.cpu().contiguous(), dtype=np.float32)
    if Y_UP:
        arr = np.flip(arr, axis=0).copy()
    return arr


def _arr_to_image(arr):
    rgb = (arr[..., :3] * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def _resize(img, target_h):
    src_w, src_h = img.size
    target_w = max(1, round(src_w * target_h / src_h))
    if (src_w, src_h) != (target_w, target_h):
        return img.resize((target_w, target_h), Image.LANCZOS)
    return img


def _bw2a(black_path, white_path, out_path):
    """BW2A: recover RGBA from a black-bg / white-bg capture pair."""
    img_black = np.array(Image.open(black_path).convert("RGB")).astype(float)
    img_white = np.array(Image.open(white_path).convert("RGB")).astype(float)

    diff = img_white - img_black
    alpha = 1.0 - (np.mean(diff, axis=2) / 255.0)
    alpha = np.clip(alpha, 0, 1)

    recovered = img_black / (alpha[:, :, np.newaxis] + 1e-10)
    recovered = np.clip(recovered, 0, 255).astype(np.uint8)

    alpha_u8 = (alpha * 255).astype(np.uint8)
    rgba = np.dstack((recovered, alpha_u8))
    Image.fromarray(rgba, "RGBA").save(out_path, "PNG")
    lf.log.info(f"[ViewportExport] RGBA saved {out_path}")


# ── Panel ─────────────────────────────────────────────────────────────────────

class ViewportExportPanel(lf.ui.Panel):
    """Export viewport as JPG or PNG; PNG supports RGBA via BW2A."""

    id = "viewport_export.main_panel"
    label = "Viewport Export"
    space = lf.ui.PanelSpace.MAIN_PANEL_TAB
    order = 60
    update_interval_ms = 500

    def __init__(self):
        self._resolution_idx = 0
        self._format_idx = 0
        self._quality = 95
        self._png_compress = 6
        self._transparency = False
        self._status = ""
        self._status_color = (1.0, 1.0, 1.0, 1.0)

        # Multi-frame BW2A state
        self._bw2a_state = {
            "step": 0,
            "black": None,
            "white": None,
            "orig_bg": None,
            "out_path": None,
            "target_h": None,
        }

    def _register_draw_handler(self):
        """Register the multi-frame draw handler for BW2A capture."""
        lf.add_draw_handler("viewport_export.bw2a", self._bw2a_draw_handler)

    def _bw2a_draw_handler(self, context):
        """
        Multi-frame BW2A capture spread across draw callbacks so the renderer
        has a full frame at each background colour before we capture.

          step 1 → set black bg, wait
          step 2 → capture black, set white bg, wait
          step 3 → capture white, restore bg, run BW2A, clean up
        """
        rs = lf.get_render_settings()
        s = self._bw2a_state

        if s["step"] == 1:
            # Frame 1: switch to black bg; capture happens next frame
            s["orig_bg"] = rs.background_color
            rs.background_color = (0.0, 0.0, 0.0)
            s["step"] = 2

        elif s["step"] == 2:
            # Frame 2: black bg is now rendered — capture it, then switch to white
            self._set_status("Capturing black bg...", warning=True)
            arr = _capture_arr()
            if arr is None:
                self._set_status("Capture failed (black bg).", error=True)
                self._bw2a_abort(rs)
                return
            s["black"] = (arr[..., :3] * 255.0).clip(0, 255).astype(np.uint8)
            rs.background_color = (1.0, 1.0, 1.0)
            s["step"] = 3

        elif s["step"] == 3:
            # Frame 3: white bg is now rendered — capture it, then finish
            self._set_status("Capturing white bg...", warning=True)
            arr = _capture_arr()
            if arr is None:
                self._set_status("Capture failed (white bg).", error=True)
                self._bw2a_abort(rs)
                return
            s["white"] = (arr[..., :3] * 255.0).clip(0, 255).astype(np.uint8)

            # Restore original background immediately
            rs.background_color = s["orig_bg"]
            s["step"] = 0

            # Write temp images and run BW2A
            try:
                out_path = s["out_path"]
                out_dir = Path(out_path).parent
                black_path = str(out_dir / "render_black_bg.png")
                white_path = str(out_dir / "render_white_bg.png")

                self._set_status("Running BW2A...", warning=True)
                Image.fromarray(s["black"], "RGB").save(black_path, "PNG")
                Image.fromarray(s["white"], "RGB").save(white_path, "PNG")
                _bw2a(black_path, white_path, out_path)

                if s["target_h"]:
                    img = _resize(Image.open(out_path), s["target_h"])
                    img.save(out_path, "PNG")

                self._set_status(f"Saved: {out_path}", success=True)
                lf.log.info(f"[ViewportExport] done: {out_path}")

            except Exception as e:
                self._set_status(f"Error: {e}", error=True)
                lf.log.error(f"[ViewportExport] {e}")

            finally:
                # Unregister this handler — it's a one-shot capture
                lf.remove_draw_handler("viewport_export.bw2a")

    def _bw2a_abort(self, rs):
        """Restore background and unregister handler on failure."""
        orig = self._bw2a_state.get("orig_bg")
        if orig is not None:
            rs.background_color = orig
        self._bw2a_state["step"] = 0
        lf.remove_draw_handler("viewport_export.bw2a")

    def draw(self, ui):
        scale = ui.get_dpi_scale()

        # ── Resolution ───────────────────────────────────────────────────────
        ui.label("Resolution:")
        labels = [r[0] for r in RESOLUTIONS]
        changed, new_idx = ui.combo("##vp_resolution", self._resolution_idx, labels)
        if changed:
            self._resolution_idx = new_idx
        _, target_h = RESOLUTIONS[self._resolution_idx]
        if target_h:
            ui.text_disabled(f"Height: {target_h} px (width from viewport aspect ratio)")
        else:
            ui.text_disabled("Native viewport resolution")

        ui.spacing()
        convention = "+Y-up" if Y_UP else "-Y-up"
        ui.text_disabled(f"Y-up: {convention} (lichtfeld {lf.__version__})")
        ui.spacing()
        ui.separator()
        ui.spacing()

        # ── Format ───────────────────────────────────────────────────────────
        ui.label("Format:")
        changed, new_idx = ui.combo("##vp_format", self._format_idx, FORMATS)
        if changed:
            self._format_idx = new_idx
        ui.spacing()

        if self._format_idx == 0:  # JPG
            ui.label("JPG Quality:")
            changed, val = ui.slider_int("##vp_quality", self._quality, 1, 100)
            if changed:
                self._quality = val
        else:  # PNG
            ui.label("PNG Compression (0 = none, 9 = max):")
            changed, val = ui.slider_int("##vp_compress", self._png_compress, 0, 9)
            if changed:
                self._png_compress = val
            ui.spacing()
            changed, val = ui.checkbox("Transparency (RGBA)", self._transparency)
            if changed:
                self._transparency = val
            if self._transparency:
                ui.text_disabled("  Captures black bg + white bg -> BW2A alpha")

        ui.spacing()
        ui.separator()
        ui.spacing()

        fmt_label = FORMATS[self._format_idx]
        if ui.button_styled(f"Export {fmt_label}", "primary", (-1, 32 * scale)):
            self._do_export()

        if self._status:
            ui.spacing()
            ui.text_colored(self._status, self._status_color)

    def _do_export(self):
        is_png = self._format_idx == 1
        _, target_h = RESOLUTIONS[self._resolution_idx]
        default_name = "viewport_export.png" if is_png else "viewport_export.jpg"

        if is_png:
            path = _save_dialog(default_name, "Save Viewport as PNG",
                                "PNG Image (*.png)|*.png", "png")
        else:
            path = _save_dialog(default_name, "Save Viewport as JPG",
                                "JPEG Image (*.jpg)|*.jpg", "jpg")
        if not path:
            path = _default_path(default_name)

        ext = ".png" if is_png else ".jpg"
        if not path.lower().endswith(ext):
            path += ext

        if is_png and self._transparency:
            # ── Multi-frame BW2A via draw handler ─────────────────────────
            self._bw2a_state.update({
                "step": 1,
                "black": None,
                "white": None,
                "orig_bg": None,
                "out_path": path,
                "target_h": target_h,
            })
            self._set_status("Starting BW2A capture...", warning=True)
            self._register_draw_handler()

        else:
            # ── Normal single capture ─────────────────────────────────────
            try:
                self._set_status("Capturing...", warning=True)
                arr = _capture_arr()
                if arr is None:
                    self._set_status("Capture failed.", error=True)
                    return
                img = _arr_to_image(arr)
                if target_h:
                    img = _resize(img, target_h)
                if is_png:
                    img.save(path, "PNG", compress_level=self._png_compress)
                else:
                    img.save(path, "JPEG", quality=self._quality)

                self._set_status(f"Saved: {path}", success=True)
                lf.log.info(f"[ViewportExport] done: {path}")

            except Exception as e:
                self._set_status(f"Error: {e}", error=True)
                lf.log.error(f"[ViewportExport] {e}")

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
