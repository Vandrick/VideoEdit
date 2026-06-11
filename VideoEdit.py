import json
import shutil
import subprocess
import sys
import ctypes
import importlib
import io
import gc
import time
import threading
from pathlib import Path

import pygame
from PIL import Image, ImageEnhance, ImageGrab, ImageTk
from tkinter import Tk, Toplevel, Label, Entry, Button, Frame, StringVar, Scale, HORIZONTAL, OptionMenu, Text, filedialog, messagebox

TEMP_DIR = Path("temp_frames")
APPEND_TEMP_DIR = TEMP_DIR / "_append_video"
BG = (18, 18, 18)
PANEL = (28, 28, 28)
TEXT = (235, 235, 235)
ACCENT = (255, 255, 255)
CHECKER_LIGHT = (178, 178, 178)
CHECKER_DARK = (112, 112, 112)
CHECKER_SIZE = 16
PREVIEW_BACKGROUNDS = ("Checker", "Black", "White")

WINDOW_W = 1400
WINDOW_H = 900
TIMELINE_H = 150
TOP_BAR_H = 50
PREVIEW_PAD = 12
BASE_THUMB_H = 72
SELECTED_SCALE = 1.7
SCROLL_FRICTION = 0.90
KEY_REPEAT_DELAY_MS = 180
KEY_REPEAT_INTERVAL_MS = 45
DRAG_MULTIPLIER = 1.0
CACHE_RADIUS = 160
THUMB_SPACING = 8
TIMELINE_SIDE_PAD = 20
FILE_RETRY_COUNT = 12
FILE_RETRY_DELAY = 0.08
SUPPORTED_VIDEO_TYPES = ".mp4 .mov .avi .mkv .webm .m4v .gif"
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".gif"}
DEFAULT_IMAGE_FPS = 16.0
SUPPORTED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
RIFE_DOWNLOAD_URL = "https://github.com/nihui/rife-ncnn-vulkan/releases"
RIFE_INPUT_DIR = TEMP_DIR / "_rife_input"
RIFE_OUTPUT_DIR = TEMP_DIR / "_rife_output"

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002
    GHND = 0x0042
    DROPEFFECT_COPY = 1

    class DROPFILES(ctypes.Structure):
        _fields_ = [
            ("pFiles", ctypes.c_uint32),
            ("pt_x", ctypes.c_long),
            ("pt_y", ctypes.c_long),
            ("fNC", ctypes.c_int),
            ("fWide", ctypes.c_int),
        ]

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    shell32 = ctypes.windll.shell32

    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_int
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_int
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_int
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    user32.RegisterClipboardFormatW.restype = ctypes.c_uint
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    user32.IsClipboardFormatAvailable.restype = ctypes.c_int
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t

    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_int
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p

    shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
    shell32.DragQueryFileW.restype = ctypes.c_uint


def set_status_error_safe(app, message):
    try:
        app.set_status(message)
    except Exception:
        pass


def set_image_clipboard_from_path(path):
    if not IS_WINDOWS:
        return False

    try:
        image = Image.open(path).convert("RGB")
        output = io.BytesIO()
        image.save(output, format="BMP")
        data = output.getvalue()[14:]
        output.close()

        hglobal = kernel32.GlobalAlloc(GHND, len(data))
        if not hglobal:
            return False

        ptr = kernel32.GlobalLock(hglobal)
        if not ptr:
            kernel32.GlobalFree(hglobal)
            return False

        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(hglobal)

        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(hglobal)
            return False

        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(8, hglobal):  # CF_DIB
                kernel32.GlobalFree(hglobal)
                return False
            hglobal = None
            return True
        finally:
            user32.CloseClipboard()
            if hglobal:
                kernel32.GlobalFree(hglobal)
    except Exception:
        return False


def set_png_clipboard_from_path(path):
    if not IS_WINDOWS:
        return False

    try:
        png_format = user32.RegisterClipboardFormatW("PNG")
        if not png_format:
            return False

        image = Image.open(path).convert("RGBA")
        output = io.BytesIO()
        image.save(output, format="PNG")
        data = output.getvalue()
        output.close()

        hglobal = kernel32.GlobalAlloc(GHND, len(data))
        if not hglobal:
            return False

        ptr = kernel32.GlobalLock(hglobal)
        if not ptr:
            kernel32.GlobalFree(hglobal)
            return False

        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(hglobal)

        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(hglobal)
            return False

        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(png_format, hglobal):
                kernel32.GlobalFree(hglobal)
                return False
            hglobal = None
            return True
        finally:
            user32.CloseClipboard()
            if hglobal:
                kernel32.GlobalFree(hglobal)
    except Exception:
        return False


def get_image_from_clipboard():
    png_image = get_png_image_from_clipboard()
    if png_image is not None:
        return png_image

    try:
        data = ImageGrab.grabclipboard()
        if isinstance(data, Image.Image):
            return data
    except Exception:
        pass
    return None


def get_png_image_from_clipboard():
    if not IS_WINDOWS:
        return None

    try:
        png_format = user32.RegisterClipboardFormatW("PNG")
        if not png_format or not user32.IsClipboardFormatAvailable(png_format):
            return None
        if not user32.OpenClipboard(None):
            return None

        try:
            handle = user32.GetClipboardData(png_format)
            if not handle:
                return None
            size = kernel32.GlobalSize(handle)
            ptr = kernel32.GlobalLock(handle)
            if not ptr or not size:
                return None
            try:
                data = ctypes.string_at(ptr, size)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return None


def set_file_clipboard(paths):
    if not IS_WINDOWS:
        return False

    file_list = " ".join(str(Path(p).resolve()) for p in paths) + "  "
    data = file_list.encode("utf-16le")
    header_size = ctypes.sizeof(DROPFILES)
    total_size = header_size + len(data)

    hglobal = kernel32.GlobalAlloc(GHND, total_size)
    if not hglobal:
        return False

    ptr = kernel32.GlobalLock(hglobal)
    if not ptr:
        kernel32.GlobalFree(hglobal)
        return False

    ctypes.memset(ptr, 0, total_size)
    dropfiles = DROPFILES.from_address(ptr)
    dropfiles.pFiles = header_size
    dropfiles.fWide = 1
    ctypes.memmove(ptr + header_size, data, len(data))
    kernel32.GlobalUnlock(hglobal)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(hglobal)
        return False

    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_HDROP, hglobal):
            kernel32.GlobalFree(hglobal)
            return False
        hglobal = None
        return True
    finally:
        user32.CloseClipboard()
        if hglobal:
            kernel32.GlobalFree(hglobal)


def get_file_clipboard_paths():
    if not IS_WINDOWS:
        return []
    if not user32.OpenClipboard(None):
        return []

    paths = []
    try:
        handle = user32.GetClipboardData(CF_HDROP)
        if not handle:
            return []

        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        for i in range(count):
            length = shell32.DragQueryFileW(handle, i, None, 0)
            buf = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(handle, i, buf, length + 1)
            paths.append(buf.value)
        return paths
    finally:
        user32.CloseClipboard()


class FrameEditorApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Video Frame Editor")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 18)
        self.small_font = pygame.font.SysFont("arial", 14)

        self.video_path = None
        self.frames = []
        self.frame_paths = []
        self.current_index = 0
        self.fps = 30.0
        self.retarget_width = None
        self.retarget_height = None
        self.retarget_fps = None
        self.preview_popup = None
        self.retarget_popup = None

        self.full_cache = {}
        self.thumb_cache = {}
        self.large_thumb_cache = {}

        self.base_thumb_sizes = []
        self.large_thumb_sizes = []
        self.prefix_positions = []
        self.timeline_total_width = 0

        self.scroll_x = 0.0
        self.scroll_velocity = 0.0
        self.dragging_timeline = False
        self.last_mouse_x = 0
        self.last_drag_dx = 0.0
        self.click_candidate = False
        self.click_down_pos = (0, 0)

        self.preview_zoom = 1.0
        self.preview_offset = [0.0, 0.0]
        self.dragging_preview = False
        self.preview_drag_last = (0, 0)

        self.left_held = False
        self.right_held = False
        self.left_next_repeat = 0
        self.right_next_repeat = 0

        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True
        self.status_message = ""
        self.status_until = 0
        self.loading_message = ""
        self.file_menu_open = False
        self.active_menu = None
        self.menu_rects = {}
        self.color_popup = None
        self.color_range_popup = None
        self.magic_outline_popup = None
        self.color_range_image_sampler = None
        self.color_reference_image = None
        self.color_reference_label = ""
        self.color_wheel_photo = None
        self.color_tool_refresh = None
        self.color_match_method = "HM"
        self.color_blend_prev_weight = 25.0
        self.color_blend_current_weight = 50.0
        self.color_blend_next_weight = 25.0
        self.mask_edit_mode = False
        self.mask_paint_mode = "restore"
        self.mask_brush_size = 12
        self.mask_dragging = False
        self.wand_mode = False
        self.wand_selection = None
        self.wand_tolerance = 32
        self.wand_dragging = False
        self.wand_start_pos = None
        self.wand_start_tolerance = 32
        self.wand_combine_mode = "replace"
        self.wand_drag_base = None
        self.wand_last_drag_tolerance = None
        self.wand_zone_cache = {}
        self.wand_zone_lock = threading.Lock()
        self.wand_preload_thread = None
        self.wand_preload_targets = []
        self.wand_preload_running = False
        self.preview_background = "Checker"
        self.background_toggle_rect = pygame.Rect(0, 0, 120, 34)
        self.rembg_settings_popup = None
        self.rembg_model = "isnet-anime"
        self.rembg_alpha_matting = True
        self.rembg_fg_threshold = 240
        self.rembg_bg_threshold = 10
        self.rembg_erode_size = 10
        self.rembg_sessions = {}
        self.ffmpeg_help_popup = None
        self.rife_help_popup = None
        self.rife_popup = None
        self.active_tool = None

        self.tk_root = Tk()
        self.tk_root.withdraw()
        self.check_ffmpeg_on_startup()

    # ---------- tool modes ----------
    def clear_active_tool(self, tool_name):
        if self.active_tool == tool_name:
            self.active_tool = None

    def close_animation_preview(self):
        popup = self.preview_popup
        self.preview_popup = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        self.clear_active_tool("preview")

    def close_color_tools(self):
        popup = self.color_popup
        self.color_popup = None
        self.color_tool_refresh = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        self.clear_active_tool("color")

    def close_color_range_tools(self):
        popup = self.color_range_popup
        self.color_range_popup = None
        self.color_range_image_sampler = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        self.clear_active_tool("color_range")

    def close_rembg_settings(self):
        popup = self.rembg_settings_popup
        self.rembg_settings_popup = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        self.clear_active_tool("rembg_settings")

    def close_magic_outline_tools(self):
        popup = self.magic_outline_popup
        self.magic_outline_popup = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        self.clear_active_tool("magic_outline")

    def set_active_tool(self, tool_name):
        if self.active_tool == tool_name:
            return True

        previous = self.active_tool
        if previous == "mask":
            self.mask_edit_mode = False
            self.mask_dragging = False
        elif previous == "wand":
            self.wand_mode = False
            self.wand_dragging = False
            self.wand_start_pos = None
            self.wand_drag_base = None
        elif previous == "preview":
            self.close_animation_preview()
        elif previous == "color":
            self.close_color_tools()
        elif previous == "color_range":
            self.close_color_range_tools()
        elif previous == "rembg_settings":
            self.close_rembg_settings()
        elif previous == "magic_outline":
            self.close_magic_outline_tools()

        self.active_tool = tool_name
        return True

    def reset_tools_for_new_media(self):
        self.close_animation_preview()
        self.close_color_tools()
        self.close_color_range_tools()
        self.close_rembg_settings()
        self.close_magic_outline_tools()
        self.active_tool = None
        self.mask_edit_mode = False
        self.mask_paint_mode = "restore"
        self.mask_dragging = False
        self.mask_brush_size = 12
        self.wand_mode = False
        self.wand_selection = None
        self.wand_tolerance = 32
        self.wand_dragging = False
        self.wand_start_pos = None
        self.wand_start_tolerance = 32
        self.wand_combine_mode = "replace"
        self.wand_drag_base = None
        self.wand_last_drag_tolerance = None
        with self.wand_zone_lock:
            self.wand_zone_cache.clear()
            self.wand_preload_targets = []
            self.wand_preload_running = False

    # ---------- ffmpeg ----------
    def app_search_dirs(self):
        dirs = [Path.cwd()]
        if getattr(sys, "frozen", False):
            dirs.append(Path(sys.executable).resolve().parent)
        else:
            dirs.append(Path(__file__).resolve().parent)
        unique_dirs = []
        for folder in dirs:
            if folder not in unique_dirs:
                unique_dirs.append(folder)
        return unique_dirs

    def find_app_tool(self, name):
        names = [name]
        if IS_WINDOWS and not name.lower().endswith(".exe"):
            names.insert(0, f"{name}.exe")
        for folder in self.app_search_dirs():
            for candidate_name in names:
                candidate = folder / candidate_name
                if candidate.exists():
                    return str(candidate)
                for child in (
                    folder / "tools" / candidate_name,
                    folder / "tools" / "rife-ncnn-vulkan" / candidate_name,
                    folder / "rife-ncnn-vulkan" / candidate_name,
                ):
                    if child.exists():
                        return str(child)
        return shutil.which(name)

    def has_ffmpeg_tools(self):
        return bool(self.find_app_tool("ffmpeg") and self.find_app_tool("ffprobe"))

    def get_ffmpeg_tool(self, name):
        tool = self.find_app_tool(name)
        if not tool:
            self.show_ffmpeg_missing_help()
            self.set_status("FFmpeg not found", 5000)
            return None
        return tool

    def build_ffmpeg_install_message(self):
        working_dir = Path.cwd().resolve()
        curl_path = shutil.which("curl")
        wget_path = shutil.which("wget")
        lines = [
            "FFmpeg was not found.",
            "",
            f"VideoEdit looked in the current working folder and on PATH.",
            f"Current working folder:",
            str(working_dir),
            "",
        ]

        if curl_path or wget_path:
            downloader = "curl" if curl_path else "wget"
            download_line = (
                f'curl.exe -L "{FFMPEG_ZIP_URL}" -o $zip'
                if downloader == "curl"
                else f'wget.exe "{FFMPEG_ZIP_URL}" -O $zip'
            )
            lines.extend(
                [
                    f"{downloader} was found on PATH. Open PowerShell, paste this command, then restart VideoEdit:",
                    "",
                    f'Set-Location -LiteralPath "{working_dir}"',
                    '$ErrorActionPreference = "Stop"',
                    '$zip = Join-Path (Get-Location) "ffmpeg-release-essentials.zip"',
                    '$tmp = Join-Path (Get-Location) "ffmpeg_extract"',
                    download_line,
                    'Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue',
                    'Expand-Archive $zip -DestinationPath $tmp -Force',
                    '$bin = Get-ChildItem $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1 -ExpandProperty DirectoryName',
                    'Copy-Item (Join-Path $bin "ffmpeg.exe") (Join-Path (Get-Location) "ffmpeg.exe") -Force',
                    'Copy-Item (Join-Path $bin "ffprobe.exe") (Join-Path (Get-Location) "ffprobe.exe") -Force',
                    'Remove-Item $tmp -Recurse -Force',
                    'Remove-Item $zip -Force',
                    '.\\ffmpeg.exe -version',
                ]
            )
        else:
            lines.extend(
                [
                    "curl and wget were not found on PATH.",
                    "",
                    "Download the Windows release essentials ZIP here:",
                    FFMPEG_ZIP_URL,
                    "",
                    "Extract the ZIP, open its bin folder, then copy these files into the current working folder above:",
                    "ffmpeg.exe",
                    "ffprobe.exe",
                    "",
                    "Restart VideoEdit after copying them.",
                ]
            )

        return "\n".join(lines)

    def show_ffmpeg_missing_help(self):
        if self.ffmpeg_help_popup is not None and self.ffmpeg_help_popup.winfo_exists():
            self.ffmpeg_help_popup.lift()
            return

        popup = Toplevel(self.tk_root)
        popup.title("FFmpeg Not Found")
        popup.geometry("820x520")
        popup.resizable(True, True)
        self.ffmpeg_help_popup = popup

        Label(popup, text="FFmpeg is required to open/export videos and GIFs.").pack(anchor="w", padx=12, pady=(12, 6))
        text = Text(popup, wrap="word", height=22)
        text.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        text.insert("1.0", self.build_ffmpeg_install_message())

        buttons = Frame(popup)
        buttons.pack(fill="x", padx=12, pady=(0, 12))

        def copy_text():
            self.tk_root.clipboard_clear()
            self.tk_root.clipboard_append(text.get("1.0", "end-1c"))
            self.set_status("Copied FFmpeg instructions")

        def close_popup():
            if self.ffmpeg_help_popup is popup:
                self.ffmpeg_help_popup = None
            popup.destroy()

        Button(buttons, text="Copy Instructions", command=copy_text).pack(side="left")
        Button(buttons, text="Close", command=close_popup).pack(side="right")
        popup.protocol("WM_DELETE_WINDOW", close_popup)
        self.set_status("FFmpeg not found; install instructions opened", 5000)

    def check_ffmpeg_on_startup(self):
        if not self.has_ffmpeg_tools():
            self.show_ffmpeg_missing_help()

    # ---------- RIFE ----------
    def find_rife_tool(self):
        return self.find_app_tool("rife-ncnn-vulkan")

    def build_rife_install_message(self):
        working_dir = Path.cwd().resolve()
        return "\n".join(
            [
                "RIFE was not found.",
                "",
                "VideoEdit looks for rife-ncnn-vulkan.exe beside the app, in a tools folder, or on PATH.",
                "",
                "Download the portable Windows build here:",
                RIFE_DOWNLOAD_URL,
                "",
                "Extract it, then either:",
                f"1. Copy rife-ncnn-vulkan.exe and its models folder into {working_dir}",
                f"2. Or put the extracted folder at {working_dir}\\tools\\rife-ncnn-vulkan",
                "",
                "The ncnn Vulkan build is portable and does not need CUDA or PyTorch.",
                "Restart VideoEdit after placing the files.",
            ]
        )

    def show_rife_missing_help(self):
        if self.rife_help_popup is not None and self.rife_help_popup.winfo_exists():
            self.rife_help_popup.lift()
            return

        popup = Toplevel(self.tk_root)
        popup.title("RIFE Not Found")
        popup.geometry("760x420")
        popup.resizable(True, True)
        self.rife_help_popup = popup

        Label(popup, text="RIFE interpolation requires rife-ncnn-vulkan.").pack(anchor="w", padx=12, pady=(12, 6))
        text = Text(popup, wrap="word", height=18)
        text.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        text.insert("1.0", self.build_rife_install_message())

        buttons = Frame(popup)
        buttons.pack(fill="x", padx=12, pady=(0, 12))

        def copy_text():
            self.tk_root.clipboard_clear()
            self.tk_root.clipboard_append(text.get("1.0", "end-1c"))
            self.set_status("Copied RIFE instructions")

        def close_popup():
            if self.rife_help_popup is popup:
                self.rife_help_popup = None
            popup.destroy()

        Button(buttons, text="Copy Instructions", command=copy_text).pack(side="left")
        Button(buttons, text="Close", command=close_popup).pack(side="right")
        popup.protocol("WM_DELETE_WINDOW", close_popup)
        self.set_status("RIFE not found; install instructions opened", 5000)

    def detect_fps(self, file_path):
        try:
            ffprobe = self.get_ffmpeg_tool("ffprobe")
            if not ffprobe:
                return 30.0
            cmd = [
                ffprobe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "json",
                str(file_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            rate = data["streams"][0]["r_frame_rate"]
            num, den = map(int, rate.split("/"))
            return (num / den) if den else 30.0
        except Exception:
            return 30.0

    def extract_frames_to_dir(self, video_path, output_dir, clear_output=True):
        ffmpeg = self.get_ffmpeg_tool("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg.exe was not found")
        if clear_output and output_dir.exists():
            result = self.retry_file_operation("clear temporary frames", lambda: shutil.rmtree(output_dir), output_dir)
            if result is None and output_dir.exists():
                raise RuntimeError("Could not clear temporary frames")
        output_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, "-y", "-i", str(video_path), str(output_dir / "frame_%06d.png")], check=True)

    def extract_frames(self, video_path):
        self.extract_frames_to_dir(video_path, TEMP_DIR, clear_output=True)

    def force_redraw(self):
        self.screen.fill(BG)
        self.draw_top_bar()
        self.draw_preview()
        self.draw_timeline()
        if self.active_menu is not None:
            self.draw_active_menu()
        pygame.display.flip()

    def open_video_path(self, path):
        path = Path(path)
        if not path.exists():
            self.set_status("File not found")
            return
        if path.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
            self.set_status("Unsupported video or animation file")
            return
        if not self.has_ffmpeg_tools():
            self.show_ffmpeg_missing_help()
            return

        self.close_menus()
        self.reset_tools_for_new_media()
        self.loading_message = f"Opening {path.name}..."
        self.force_redraw()

        self.video_path = path
        self.loading_message = "Reading video info..."
        self.force_redraw()
        self.fps = self.detect_fps(self.video_path)
        self.loading_message = "Extracting frames..."
        self.force_redraw()
        self.extract_frames(self.video_path)

        self.frame_paths = sorted(TEMP_DIR.glob("frame_*.png"))
        self.frames = [p.name for p in self.frame_paths]
        self.current_index = 0
        self.initialize_retarget_settings()
        self.scroll_x = 0.0
        self.scroll_velocity = 0.0
        self.preview_zoom = 1.0
        self.preview_offset = [0.0, 0.0]

        self.full_cache.clear()
        self.thumb_cache.clear()
        self.large_thumb_cache.clear()
        self.base_thumb_sizes = []
        self.large_thumb_sizes = []
        self.prefix_positions = []
        self.timeline_total_width = 0
        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True

        self.loading_message = "Building timeline..."
        self.force_redraw()
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.center_selected()
        self.schedule_wand_zone_preload()
        self.loading_message = ""
        self.set_status(f"Opened {path.name}")

    def open_video(self):
        self.loading_message = "Opening video..."
        self.force_redraw()

        path = filedialog.askopenfilename(
            title="Open video",
            filetypes=[("Video Files", SUPPORTED_VIDEO_TYPES)],
        )
        if not path:
            self.loading_message = ""
            return

        self.open_video_path(path)

    def open_image_path(self, path):
        path = Path(path)
        if not path.exists():
            self.set_status("File not found")
            return
        if path.suffix.lower() not in SUPPORTED_IMAGE_TYPES:
            self.set_status("Unsupported image file")
            return

        self.close_menus()
        self.reset_tools_for_new_media()
        self.loading_message = f"Opening {path.name}..."
        self.force_redraw()

        if TEMP_DIR.exists():
            result = self.retry_file_operation("clear temporary frames", lambda: shutil.rmtree(TEMP_DIR), TEMP_DIR)
            if result is None and TEMP_DIR.exists():
                self.loading_message = ""
                return
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        image = self.open_image_copy(path, "RGBA", "open image")
        if image is None:
            self.loading_message = ""
            return
        if not self.save_image_retry(image, TEMP_DIR / "frame_000001.png", "save image frame"):
            self.loading_message = ""
            return

        self.video_path = None
        self.fps = DEFAULT_IMAGE_FPS
        self.frame_paths = sorted(TEMP_DIR.glob("frame_*.png"))
        self.frames = [p.name for p in self.frame_paths]
        self.current_index = 0
        self.initialize_retarget_settings()
        self.scroll_x = 0.0
        self.scroll_velocity = 0.0
        self.preview_zoom = 1.0
        self.preview_offset = [0.0, 0.0]

        self.full_cache.clear()
        self.thumb_cache.clear()
        self.large_thumb_cache.clear()
        with self.wand_zone_lock:
            self.wand_zone_cache.clear()
            self.wand_preload_targets = []
        self.base_thumb_sizes = []
        self.large_thumb_sizes = []
        self.prefix_positions = []
        self.timeline_total_width = 0
        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True

        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.center_selected()
        self.schedule_wand_zone_preload()
        self.loading_message = ""
        self.set_status(f"Opened image at {DEFAULT_IMAGE_FPS:g} FPS")

    def reload_video(self):
        if self.video_path is None:
            self.set_status("No source video to reload")
            return
        self.open_video_path(self.video_path)

    def make_even(self, value):
        value = max(2, int(value))
        return value if value % 2 == 0 else value + 1

    def get_current_frame_size(self):
        if not self.frame_paths:
            return None
        index = max(0, min(self.current_index, len(self.frame_paths) - 1))
        image = self.open_image_copy(self.frame_paths[index], "RGBA", "read frame size")
        if image is None:
            return None
        return image.size

    def initialize_retarget_settings(self):
        size = self.get_current_frame_size()
        if size is None:
            self.retarget_width = None
            self.retarget_height = None
            self.retarget_fps = None
            return

        self.retarget_width = self.make_even(size[0])
        self.retarget_height = self.make_even(size[1])
        self.retarget_fps = max(1.0, float(self.fps))

    def get_retarget_settings(self):
        if not self.frames:
            return None
        if self.retarget_width is None or self.retarget_height is None or self.retarget_fps is None:
            self.initialize_retarget_settings()
        return self.retarget_width, self.retarget_height, self.retarget_fps

    def retarget_size_fps(self):
        if not self.frames:
            self.set_status("Open a video before retargeting")
            return

        width, height, fps = self.get_retarget_settings()

        if self.retarget_popup is not None and self.retarget_popup.winfo_exists():
            self.retarget_popup.lift()
            return

        popup = Toplevel(self.tk_root)
        popup.title("Retarget Size/FPS")
        popup.resizable(False, False)
        self.retarget_popup = popup

        width_var = StringVar(value=str(width))
        height_var = StringVar(value=str(height))
        fps_var = StringVar(value=f"{fps:.3f}")
        error_var = StringVar(value="")

        fields = Frame(popup, padx=14, pady=12)
        fields.pack()

        def add_row(row, label, variable):
            Label(fields, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=4)
            entry = Entry(fields, textvariable=variable, width=14)
            entry.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
            return entry

        width_entry = add_row(0, "Width", width_var)
        add_row(1, "Height", height_var)
        add_row(2, "FPS", fps_var)
        Label(fields, textvariable=error_var, fg="red", anchor="w").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        buttons = Frame(fields)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))

        def close_popup():
            if self.retarget_popup is popup:
                self.retarget_popup = None
            popup.destroy()

        def apply_values():
            try:
                new_width = int(width_var.get())
                new_height = int(height_var.get())
                new_fps = float(fps_var.get())
            except ValueError:
                error_var.set("Use numbers for width, height, and FPS.")
                return

            if new_width < 2 or new_height < 2 or new_fps <= 0:
                error_var.set("Width/height must be 2+, FPS must be above 0.")
                return

            self.retarget_width = self.make_even(new_width)
            self.retarget_height = self.make_even(new_height)
            self.retarget_fps = float(new_fps)
            self.set_status(f"Retarget {self.retarget_width}x{self.retarget_height} @ {self.retarget_fps:.3f} FPS")
            close_popup()

        Button(buttons, text="Cancel", command=close_popup).pack(side="right", padx=(8, 0))
        Button(buttons, text="Apply", command=apply_values).pack(side="right")

        popup.protocol("WM_DELETE_WINDOW", close_popup)
        popup.bind("<Return>", lambda _event: apply_values())
        popup.bind("<Escape>", lambda _event: close_popup())
        width_entry.focus_set()

    def show_animation_preview(self):
        if not self.frames:
            self.set_status("Open a video before previewing")
            return

        if self.active_tool == "preview" and self.preview_popup is not None and self.preview_popup.winfo_exists():
            self.preview_popup.lift()
            return
        self.set_active_tool("preview")

        width, height, fps = self.get_retarget_settings()
        if self.preview_popup is not None and self.preview_popup.winfo_exists():
            self.preview_popup.destroy()

        popup = Toplevel(self.tk_root)
        popup.title(f"Preview - {width}x{height} @ {fps:.3f} FPS")
        popup.resizable(False, False)
        image_label = Label(popup, bg="black")
        image_label.pack()
        image_label.configure(text="Preparing preview...", fg="white", compound="center")

        self.preview_popup = popup

        def close_preview():
            self.close_animation_preview()

        popup.protocol("WM_DELETE_WINDOW", close_preview)

        preview_frames = []
        try:
            for frame_number, path in enumerate(self.frame_paths, start=1):
                if self.preview_popup is not popup or not popup.winfo_exists():
                    return

                image_label.configure(text=f"Preparing preview {frame_number}/{len(self.frame_paths)}")
                popup.update_idletasks()
                popup.update()

                image = self.open_image_copy(path, "RGB", "open preview frame")
                if image is None:
                    close_preview()
                    return
                image = image.resize((width, height), Image.Resampling.LANCZOS)
                preview_frames.append(ImageTk.PhotoImage(image))
        except MemoryError:
            close_preview()
            self.set_status("Preview too large to fit in memory")
            return

        if not preview_frames:
            close_preview()
            self.set_status("No frames available for preview")
            return

        image_label.configure(text="", image=preview_frames[0])
        image_label.image = preview_frames[0]
        image_label.preview_frames = preview_frames
        start_time = time.perf_counter()
        frame_state = {"index": 0}

        def draw_next_frame():
            if self.preview_popup is not popup or not popup.winfo_exists():
                return

            frame_count = len(preview_frames)
            clip_duration = frame_count / fps
            elapsed = (time.perf_counter() - start_time) % clip_duration
            target_index = int(elapsed * fps) % frame_count

            if target_index != frame_state["index"]:
                photo = preview_frames[target_index]
                image_label.configure(image=photo)
                image_label.image = photo
                frame_state["index"] = target_index

            schedule_elapsed = (time.perf_counter() - start_time) % clip_duration
            next_frame_at = ((int(schedule_elapsed * fps) + 1) / fps)
            delay_ms = max(1, int((next_frame_at - schedule_elapsed) * 1000))
            popup.after(delay_ms, draw_next_frame)

        draw_next_frame()
        self.set_status("Preview playing")

    def export_video(self):
        if not self.frames:
            return
        ffmpeg = self.get_ffmpeg_tool("ffmpeg")
        if not ffmpeg:
            return
        save_path = filedialog.asksaveasfilename(
            title="Save video",
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4")],
        )
        if not save_path:
            return

        temp_video = TEMP_DIR / "_video_only_export.mp4"
        width, height, output_fps = self.get_retarget_settings()

        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-framerate",
                    str(output_fps),
                    "-i",
                    str(TEMP_DIR / "frame_%06d.png"),
                    "-vf",
                    f"scale={width}:{height}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(temp_video),
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            self.show_file_error("export video", temp_video, exc)
            return

        if self.video_path is not None:
            try:
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(temp_video),
                        "-i",
                        str(self.video_path),
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a?",
                        "-c:v",
                        "copy",
                        "-c:a",
                        "aac",
                        "-shortest",
                        save_path,
                    ],
                    check=True,
                )
                self.set_status("Exported video with original audio")
            except subprocess.CalledProcessError:
                if not self.copy_path_retry(temp_video, save_path, "save exported video"):
                    return
                self.set_status("Exported video only; audio copy failed")
        else:
            if not self.copy_path_retry(temp_video, save_path, "save exported video"):
                return
            self.set_status("Exported video only")

    def export_high_quality_gif(self):
        if not self.frames:
            return
        ffmpeg = self.get_ffmpeg_tool("ffmpeg")
        if not ffmpeg:
            return
        save_path = filedialog.asksaveasfilename(
            title="Save high quality GIF",
            defaultextension=".gif",
            filetypes=[("GIF Animation", "*.gif")],
        )
        if not save_path:
            return

        width, height, output_fps = self.get_retarget_settings()
        filter_graph = (
            f"fps={output_fps},scale={width}:{height}:flags=lanczos,"
            "split[s0][s1];"
            "[s0]palettegen=max_colors=256:reserve_transparent=1[p];"
            "[s1][p]paletteuse=dither=sierra2_4a:alpha_threshold=128"
        )
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-framerate",
                    str(output_fps),
                    "-i",
                    str(TEMP_DIR / "frame_%06d.png"),
                    "-filter_complex",
                    filter_graph,
                    "-loop",
                    "0",
                    save_path,
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            self.show_file_error("export GIF", save_path, exc)
            return
        self.set_status("Exported high quality GIF")

    def clear_rife_work_dirs(self):
        for folder in (RIFE_INPUT_DIR, RIFE_OUTPUT_DIR):
            if folder.exists():
                result = self.retry_file_operation(f"clear {folder.name}", lambda target=folder: shutil.rmtree(target), folder)
                if result is None and folder.exists():
                    return False
            folder.mkdir(parents=True, exist_ok=True)
        (RIFE_OUTPUT_DIR / "ext").mkdir(parents=True, exist_ok=True)
        return True

    def stage_rife_input_frames(self):
        if not self.clear_rife_work_dirs():
            return False
        for i, path in enumerate(self.frame_paths, start=1):
            staged = RIFE_INPUT_DIR / f"{i:08d}.png"
            image = self.open_image_copy(path, "RGB", "open RIFE input frame")
            if image is None:
                return False
            if not self.save_image_retry(image, staged, "stage RIFE input frame"):
                return False
        return True

    def stage_rife_paths(self, paths):
        if not self.clear_rife_work_dirs():
            return False
        for i, path in enumerate(paths, start=1):
            staged = RIFE_INPUT_DIR / f"{i:08d}.png"
            image = self.open_image_copy(path, "RGB", "open RIFE blend frame")
            if image is None:
                return False
            if not self.save_image_retry(image, staged, "stage RIFE blend frame"):
                return False
        return True

    def get_rife_command(self, rife, multiplier, model_name, spatial_tta=False, temporal_tta=False, uhd_mode=False, target_count=None):
        command = [
            rife,
            "-i",
            str(RIFE_INPUT_DIR.resolve()),
            "-o",
            str(RIFE_OUTPUT_DIR.resolve()),
            "-f",
            "ext/%08d.png",
        ]
        if target_count is not None and model_name == "rife-v4":
            command.extend(["-n", str(target_count)])
        if model_name and model_name != "Default":
            command.extend(["-m", model_name])
        if spatial_tta:
            command.append("-x")
        if temporal_tta:
            command.append("-z")
        if uhd_mode:
            command.append("-u")
        return command

    def run_rife_command(self, command, rife, label):
        self.loading_message = label
        self.force_redraw()
        try:
            subprocess.run(command, cwd=str(Path(rife).resolve().parent), check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            self.loading_message = ""
            self.show_file_error("run RIFE interpolation", rife, exc)
            return None
        return sorted(RIFE_OUTPUT_DIR.rglob("*.png"))

    def apply_rife_output_frames(self, multiplier):
        output_paths = sorted(RIFE_OUTPUT_DIR.rglob("*.png"))
        if len(output_paths) < 2:
            self.set_status("RIFE did not create enough frames", 5000)
            return False

        self.release_file_caches()
        for path in sorted(TEMP_DIR.glob("frame_*.png")):
            if not self.unlink_path_retry(path, show_error=True):
                return False

        for i, path in enumerate(output_paths, start=1):
            destination = TEMP_DIR / f"frame_{i:06d}.png"
            if not self.copy_path_retry(path, destination, "copy RIFE output frame"):
                return False

        self.frame_paths = sorted(TEMP_DIR.glob("frame_*.png"))
        self.frames = [p.name for p in self.frame_paths]
        self.current_index = min(self.current_index * multiplier, max(0, len(self.frames) - 1))
        self.fps *= multiplier
        if self.retarget_fps is not None:
            self.retarget_fps *= multiplier
        self.reset_after_frame_list_change()
        self.set_status(f"RIFE interpolated to {len(self.frames)} frames @ {self.fps:.3f} FPS", 5000)
        return True

    def run_rife_interpolation(self, multiplier, model_name, spatial_tta, temporal_tta, uhd_mode):
        rife = self.find_rife_tool()
        if not rife:
            self.show_rife_missing_help()
            return

        if len(self.frames) < 2:
            self.set_status("RIFE needs at least two frames")
            return

        if multiplier != 2 and model_name != "rife-v4":
            self.set_status("RIFE 3x/4x requires the rife-v4 model", 5000)
            return

        if not self.stage_rife_input_frames():
            return

        target_count = len(self.frames) * multiplier if multiplier != 2 else None
        command = self.get_rife_command(rife, multiplier, model_name, spatial_tta, temporal_tta, uhd_mode, target_count=target_count)
        output_paths = self.run_rife_command(command, rife, f"Running RIFE {multiplier}x...")
        if output_paths is None:
            return

        self.loading_message = "Loading RIFE frames..."
        self.force_redraw()
        self.apply_rife_output_frames(multiplier)
        self.loading_message = ""

    def color_lerp_rife_frames(self, paths, left_reference_path, right_reference_path):
        try:
            import numpy as np
        except ImportError:
            self.set_status("Install numpy to use RIFE blend color lerp")
            return None

        left_reference = self.open_image_copy(left_reference_path, "RGB", "open left RIFE color reference")
        right_reference = self.open_image_copy(right_reference_path, "RGB", "open right RIFE color reference")
        if left_reference is None or right_reference is None:
            return None

        count = len(paths)
        if count == 0:
            return []

        blended_frames = []
        for i, path in enumerate(paths):
            image = self.open_image_copy(path, "RGBA", "open RIFE blend frame")
            if image is None:
                return None
            alpha = image.getchannel("A")
            base_rgb = image.convert("RGB")
            left_matched = self.apply_color_match_method(base_rgb, left_reference).convert("RGB")
            right_matched = self.apply_color_match_method(base_rgb, right_reference).convert("RGB")
            t = i / max(1, count - 1)
            left_array = np.asarray(left_matched, dtype=np.float32)
            right_array = np.asarray(right_matched, dtype=np.float32)
            result_array = np.clip(left_array * (1.0 - t) + right_array * t, 0, 255).astype("uint8")
            result = Image.fromarray(result_array, "RGB").convert("RGBA")
            result.putalpha(alpha)
            blended_frames.append(result)
        return blended_frames

    def replace_frames_with_sequence(self, sequence, status_message, current_index=0):
        prepared = []
        for item in sequence:
            if isinstance(item, Image.Image):
                prepared.append(item.convert("RGBA").copy())
            else:
                image = self.open_image_copy(item, "RGBA", "prepare replacement frame")
                if image is None:
                    return False
                prepared.append(image)

        self.release_file_caches()
        for path in sorted(TEMP_DIR.glob("frame_*.png")):
            if not self.unlink_path_retry(path, show_error=True):
                return False

        for i, image in enumerate(prepared, start=1):
            destination = TEMP_DIR / f"frame_{i:06d}.png"
            if not self.save_image_retry(image, destination, "save blended RIFE frame"):
                return False

        self.frame_paths = sorted(TEMP_DIR.glob("frame_*.png"))
        self.frames = [p.name for p in self.frame_paths]
        self.current_index = max(0, min(current_index, len(self.frames) - 1))
        self.reset_after_frame_list_change()
        self.set_status(status_message, 5000)
        return True

    def get_middle_rife_frames(self, output_paths, count=6):
        if len(output_paths) < count:
            return []
        start = max(0, (len(output_paths) - count) // 2)
        return output_paths[start:start + count]

    def run_rife_blend_from_paths(self, input_paths, left_reference_path, right_reference_path, model_name="rife-anime"):
        rife = self.find_rife_tool()
        if not rife:
            self.show_rife_missing_help()
            return None

        if not self.stage_rife_paths(input_paths):
            return None

        command = self.get_rife_command(rife, 2, model_name, target_count=len(input_paths) * 2)
        output_paths = self.run_rife_command(command, rife, "Running RIFE blend...")
        if output_paths is None:
            return None

        middle_paths = self.get_middle_rife_frames(output_paths, 6)
        if len(middle_paths) < 6:
            self.loading_message = ""
            self.set_status("RIFE blend did not create enough middle frames", 5000)
            return None

        self.loading_message = "Color matching RIFE blend..."
        self.force_redraw()
        blended = self.color_lerp_rife_frames(middle_paths, left_reference_path, right_reference_path)
        self.loading_message = ""
        return blended

    def rife_blend_selected_split(self):
        if not self.frames:
            return
        if self.current_index < 3 or (len(self.frames) - self.current_index - 1) < 3:
            self.set_status("Select a frame with at least 3 frames before and after it", 5000)
            return

        left_indices = [self.current_index - 3, self.current_index - 2, self.current_index - 1]
        right_indices = [self.current_index + 1, self.current_index + 2, self.current_index + 3]
        input_paths = [self.frame_paths[i] for i in left_indices + right_indices]
        blended = self.run_rife_blend_from_paths(input_paths, self.frame_paths[left_indices[0]], self.frame_paths[right_indices[-1]])
        if blended is None:
            return

        sequence = list(self.frame_paths[:left_indices[0] + 1]) + blended + list(self.frame_paths[right_indices[-1]:])
        self.replace_frames_with_sequence(sequence, "RIFE blended selected split", current_index=left_indices[0] + 1)

    def rife_blend_loop(self):
        if len(self.frames) < 8:
            self.set_status("RIFE loop blend needs at least 8 frames")
            return

        frame_count = len(self.frames)
        left_indices = [frame_count - 4, frame_count - 3, frame_count - 2]
        right_indices = [1, 2, 3]
        input_paths = [self.frame_paths[i] for i in left_indices + right_indices]
        blended = self.run_rife_blend_from_paths(input_paths, self.frame_paths[frame_count - 3], self.frame_paths[3])
        if blended is None:
            return

        sequence = list(self.frame_paths)
        sequence[:3] = blended[3:]
        sequence = sequence[:frame_count - 2] + blended[:3]
        self.replace_frames_with_sequence(sequence, "RIFE rebuilt loop seam", current_index=frame_count - 2)

    def open_rife_interpolation(self):
        if not self.frames:
            self.set_status("Open a video before using RIFE")
            return
        if len(self.frames) < 2:
            self.set_status("RIFE needs at least two frames")
            return
        if not self.find_rife_tool():
            self.show_rife_missing_help()
            return

        if self.rife_popup is not None and self.rife_popup.winfo_exists():
            self.rife_popup.lift()
            return

        popup = Toplevel(self.tk_root)
        popup.title("RIFE Interpolation")
        popup.resizable(False, False)
        self.rife_popup = popup

        main = Frame(popup, padx=14, pady=12)
        main.pack()

        multiplier_var = StringVar(value="2")
        model_var = StringVar(value="rife-anime")
        spatial_var = StringVar(value="Off")
        temporal_var = StringVar(value="Off")
        uhd_var = StringVar(value="Off")
        error_var = StringVar(value="")

        Label(main, text="Multiplier").grid(row=0, column=0, sticky="w", pady=4)
        OptionMenu(main, multiplier_var, "2", "3", "4").grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)

        Label(main, text="Model").grid(row=1, column=0, sticky="w", pady=4)
        OptionMenu(
            main,
            model_var,
            "Default",
            "rife-anime",
            "rife-v4.6",
            "rife-v4",
            "rife-v3.1",
            "rife-v2.4",
            "rife-v2.3",
        ).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)

        Label(main, text="Spatial TTA").grid(row=2, column=0, sticky="w", pady=4)
        OptionMenu(main, spatial_var, "Off", "On").grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=4)

        Label(main, text="Temporal TTA").grid(row=3, column=0, sticky="w", pady=4)
        OptionMenu(main, temporal_var, "Off", "On").grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=4)

        Label(main, text="UHD Mode").grid(row=4, column=0, sticky="w", pady=4)
        OptionMenu(main, uhd_var, "Off", "On").grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=4)

        Label(main, textvariable=error_var, fg="red").grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))

        buttons = Frame(main)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))

        def close_popup():
            if self.rife_popup is popup:
                self.rife_popup = None
            popup.destroy()

        def apply_rife():
            try:
                multiplier = int(multiplier_var.get())
            except ValueError:
                error_var.set("Multiplier must be a number.")
                return
            close_popup()
            self.run_rife_interpolation(
                multiplier,
                model_var.get(),
                spatial_var.get() == "On",
                temporal_var.get() == "On",
                uhd_var.get() == "On",
            )

        Button(buttons, text="Cancel", command=close_popup).pack(side="right", padx=(8, 0))
        Button(buttons, text="Interpolate", command=apply_rife).pack(side="right")
        popup.protocol("WM_DELETE_WINDOW", close_popup)
        popup.bind("<Return>", lambda _event: apply_rife())
        popup.bind("<Escape>", lambda _event: close_popup())

    # ---------- cache ----------
    def load_full_surface(self, index):
        surf = self.full_cache.get(index)
        if surf is not None:
            return surf
        surf = self.retry_file_operation(
            "load frame image",
            lambda: pygame.image.load(str(self.frame_paths[index])).convert_alpha(),
            self.frame_paths[index],
        )
        if surf is None:
            return pygame.Surface((1, 1), pygame.SRCALPHA).convert_alpha()
        self.full_cache[index] = surf
        return surf

    def build_thumb(self, index, selected=False):
        cache = self.large_thumb_cache if selected else self.thumb_cache
        if index in cache:
            return cache[index]

        full = self.load_full_surface(index)
        target_h = int(BASE_THUMB_H * (SELECTED_SCALE if selected else 1.0))
        scale = target_h / full.get_height()
        size = (max(1, int(full.get_width() * scale)), max(1, target_h))
        thumb = pygame.transform.smoothscale(full, size)
        composed = pygame.Surface(size).convert()
        self.draw_alpha_background(composed, composed.get_rect())
        composed.blit(thumb, (0, 0))
        cache[index] = composed
        return composed

    def prime_caches_near_current(self):
        if not self.frames:
            return

        start = max(0, self.current_index - CACHE_RADIUS)
        end = min(len(self.frames), self.current_index + CACHE_RADIUS + 1)
        keep = set(range(start, end))

        for i in range(start, end):
            self.load_full_surface(i)
            self.build_thumb(i, selected=False)
            if i == self.current_index:
                self.build_thumb(i, selected=True)

        for cache in (self.full_cache, self.thumb_cache, self.large_thumb_cache):
            for key in list(cache.keys()):
                if key not in keep:
                    del cache[key]

    # ---------- layout ----------
    def get_window_size(self):
        return self.screen.get_width(), self.screen.get_height()

    def get_preview_rect(self):
        w, h = self.get_window_size()
        y = TOP_BAR_H
        return pygame.Rect(PREVIEW_PAD, y + PREVIEW_PAD, w - PREVIEW_PAD * 2, h - TOP_BAR_H - TIMELINE_H - PREVIEW_PAD * 2)

    def get_timeline_rect(self):
        w, h = self.get_window_size()
        return pygame.Rect(0, h - TIMELINE_H, w, TIMELINE_H)

    def rebuild_timeline_metrics(self):
        self.base_thumb_sizes = []
        self.large_thumb_sizes = []
        self.prefix_positions = []

        x = TIMELINE_SIDE_PAD
        for i in range(len(self.frames)):
            base = self.build_thumb(i, selected=False)
            large = self.build_thumb(i, selected=True)
            self.base_thumb_sizes.append(base.get_size())
            self.large_thumb_sizes.append(large.get_size())
            self.prefix_positions.append(x)
            x += base.get_width() + THUMB_SPACING

        self.timeline_total_width = max(0, x - THUMB_SPACING + TIMELINE_SIDE_PAD)

    def get_thumb_rect(self, index):
        timeline = self.get_timeline_rect()
        center_y = timeline.y + timeline.h // 2 + 4

        if (
            index < 0
            or index >= len(self.frames)
            or index >= len(self.prefix_positions)
            or index >= len(self.base_thumb_sizes)
            or not self.large_thumb_sizes
            or self.current_index >= len(self.large_thumb_sizes)
            or self.current_index >= len(self.base_thumb_sizes)
        ):
            rect = pygame.Rect(-10000, 0, 1, 1)
            rect.centery = center_y
            return rect

        x = self.prefix_positions[index] - self.scroll_x
        selected_extra = (self.large_thumb_sizes[self.current_index][0] - self.base_thumb_sizes[self.current_index][0]) / 2

        if index == self.current_index:
            base_w, _ = self.base_thumb_sizes[index]
            large_w, large_h = self.large_thumb_sizes[index]
            x -= (large_w - base_w) / 2
            w, h = large_w, large_h
        elif index > self.current_index:
            x += selected_extra
            w, h = self.base_thumb_sizes[index]
        else:
            x -= selected_extra
            w, h = self.base_thumb_sizes[index]

        rect = pygame.Rect(int(x), 0, int(w), int(h))
        rect.centery = center_y
        return rect

    def get_max_scroll(self):
        if not self.frames:
            return 0.0
        timeline = self.get_timeline_rect()
        selected_extra = self.large_thumb_sizes[self.current_index][0] - self.base_thumb_sizes[self.current_index][0]
        return max(0.0, self.timeline_total_width + selected_extra - timeline.w + TIMELINE_SIDE_PAD * 2)

    def clamp_scroll(self):
        max_scroll = self.get_max_scroll()
        if self.scroll_x < 0:
            self.scroll_x = 0.0
            self.scroll_velocity = 0.0
        if self.scroll_x > max_scroll:
            self.scroll_x = max_scroll
            self.scroll_velocity = 0.0

    def center_selected(self):
        if not self.frames:
            return
        timeline = self.get_timeline_rect()
        selected = self.get_thumb_rect(self.current_index)
        desired = self.scroll_x + (selected.centerx - timeline.centerx)
        self.scroll_x = max(0.0, min(self.get_max_scroll(), desired))
        self.scroll_velocity = 0.0

    # ---------- preview ----------
    def clamp_preview_offset(self):
        if not self.frames:
            self.preview_offset = [0.0, 0.0]
            return

        rect = self.get_preview_rect()
        full = self.load_full_surface(self.current_index)
        img_w, img_h = full.get_size()
        fit_scale = min(rect.w / img_w, rect.h / img_h)
        scale = max(0.05, fit_scale * self.preview_zoom)
        draw_w = max(1, int(img_w * scale))
        draw_h = max(1, int(img_h * scale))

        max_x = max(0, (draw_w - rect.w) / 2)
        max_y = max(0, (draw_h - rect.h) / 2)

        self.preview_offset[0] = max(-max_x, min(max_x, self.preview_offset[0]))
        self.preview_offset[1] = max(-max_y, min(max_y, self.preview_offset[1]))

    def set_current_index(self, index):
        index = max(0, min(len(self.frames) - 1, index))
        if index == self.current_index:
            return
        self.current_index = index
        self.wand_selection = None
        self.wand_dragging = False
        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True
        self.clamp_preview_offset()
        self.prime_caches_near_current()
        self.center_selected()
        self.schedule_wand_zone_preload()
        if self.color_popup is not None and self.color_popup.winfo_exists() and self.color_tool_refresh is not None:
            self.color_tool_refresh()

    def refresh_preview_surface(self):
        if not self.frames:
            return

        rect = self.get_preview_rect()
        full = self.load_full_surface(self.current_index)
        key = (self.current_index, rect.size, round(self.preview_zoom, 4), int(self.preview_offset[0]), int(self.preview_offset[1]), self.preview_background)
        if key == self.preview_surface_key and self.preview_surface is not None:
            return

        img_w, img_h = full.get_size()
        fit_scale = min(rect.w / img_w, rect.h / img_h)
        scale = max(0.05, fit_scale * self.preview_zoom)
        draw_w = max(1, int(img_w * scale))
        draw_h = max(1, int(img_h * scale))
        scaled = pygame.transform.smoothscale(full, (draw_w, draw_h))

        surface = pygame.Surface((rect.w, rect.h)).convert()
        self.draw_alpha_background(surface, surface.get_rect(), offset=(-int(self.preview_offset[0]), -int(self.preview_offset[1])))
        x = (rect.w - draw_w) // 2 + int(self.preview_offset[0])
        y = (rect.h - draw_h) // 2 + int(self.preview_offset[1])
        surface.blit(scaled, (x, y))

        self.preview_surface = surface
        self.preview_surface_key = key
        self.needs_preview_refresh = False

    def zoom_preview(self, mouse_pos, delta):
        if not self.frames:
            return
        old_zoom = self.preview_zoom
        factor = 1.12 if delta > 0 else (1 / 1.12)
        self.preview_zoom = max(1.0, min(24.0, self.preview_zoom * factor))
        self.clamp_preview_offset()
        if self.preview_zoom != old_zoom:
            self.needs_preview_refresh = True

    def reset_preview_view(self):
        self.preview_zoom = 1.0
        self.preview_offset = [0.0, 0.0]
        self.needs_preview_refresh = True

    def set_status(self, message, duration_ms=1800):
        self.status_message = message
        self.status_until = pygame.time.get_ticks() + duration_ms

    def show_file_error(self, action, path, exc):
        target = f"\n\n{path}" if path is not None else ""
        message = f"Could not {action}.{target}\n\n{exc}"
        self.set_status(f"Could not {action}", 5000)
        try:
            messagebox.showerror("File Error", message, parent=self.tk_root)
        except Exception:
            pass

    def release_file_caches(self):
        self.full_cache.clear()
        self.thumb_cache.clear()
        self.large_thumb_cache.clear()
        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True
        gc.collect()

    def retry_file_operation(self, action, operation, path=None, show_error=True):
        last_exc = None
        for attempt in range(FILE_RETRY_COUNT):
            try:
                return operation()
            except (OSError, PermissionError) as exc:
                last_exc = exc
                self.release_file_caches()
                if attempt < FILE_RETRY_COUNT - 1:
                    time.sleep(FILE_RETRY_DELAY * (attempt + 1))
        if show_error and last_exc is not None:
            self.show_file_error(action, path, last_exc)
        return None

    def open_image_copy(self, path, mode="RGBA", action="open image"):
        def operation():
            with Image.open(path) as image:
                return image.convert(mode).copy() if mode else image.copy()

        return self.retry_file_operation(action, operation, path)

    def save_image_retry(self, image, path, action="save image"):
        def operation():
            image.save(path)
            return True

        return bool(self.retry_file_operation(action, operation, path))

    def rename_path_retry(self, src, dst):
        def operation():
            src.rename(dst)
            return True

        return bool(self.retry_file_operation("rename frame file", operation, src))

    def unlink_path_retry(self, path, show_error=True):
        def operation():
            path.unlink()
            return True

        return bool(self.retry_file_operation("delete frame file", operation, path, show_error=show_error))

    def copy_path_retry(self, src, dst, action="copy file"):
        def operation():
            shutil.copy(src, dst)
            return True

        return bool(self.retry_file_operation(action, operation, src))

    def handle_filesystem_exception(self, exc):
        self.loading_message = ""
        self.mask_dragging = False
        self.wand_dragging = False
        self.dragging_timeline = False
        self.dragging_preview = False
        self.release_file_caches()
        self.show_file_error("access a file", None, exc)

    def invalidate_frame_cache(self, index=None):
        if index is None:
            self.full_cache.clear()
            self.thumb_cache.clear()
            self.large_thumb_cache.clear()
            with self.wand_zone_lock:
                self.wand_zone_cache.clear()
        else:
            for cache in (self.full_cache, self.thumb_cache, self.large_thumb_cache):
                cache.pop(index, None)
            with self.wand_zone_lock:
                self.wand_zone_cache.pop(index, None)

        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True

    def save_edited_frame(self, index, image):
        if not self.save_image_retry(image.convert("RGBA"), self.frame_paths[index], "save frame"):
            return False
        self.invalidate_frame_cache(index)
        if index == self.current_index:
            self.schedule_wand_zone_preload()
        return True

    def draw_checkerboard(self, surface, rect, offset=(0, 0)):
        clip = surface.get_clip()
        surface.set_clip(rect)
        start_x = rect.x - ((rect.x + offset[0]) % CHECKER_SIZE)
        start_y = rect.y - ((rect.y + offset[1]) % CHECKER_SIZE)
        for y in range(start_y, rect.bottom, CHECKER_SIZE):
            for x in range(start_x, rect.right, CHECKER_SIZE):
                tile_x = (x + offset[0]) // CHECKER_SIZE
                tile_y = (y + offset[1]) // CHECKER_SIZE
                color = CHECKER_LIGHT if (tile_x + tile_y) % 2 == 0 else CHECKER_DARK
                pygame.draw.rect(surface, color, (x, y, CHECKER_SIZE, CHECKER_SIZE))
        surface.set_clip(clip)

    def draw_alpha_background(self, surface, rect, offset=(0, 0)):
        if self.preview_background == "Black":
            surface.fill((0, 0, 0), rect)
        elif self.preview_background == "White":
            surface.fill((255, 255, 255), rect)
        else:
            self.draw_checkerboard(surface, rect, offset)

    def cycle_preview_background(self):
        index = PREVIEW_BACKGROUNDS.index(self.preview_background)
        self.preview_background = PREVIEW_BACKGROUNDS[(index + 1) % len(PREVIEW_BACKGROUNDS)]
        self.thumb_cache.clear()
        self.large_thumb_cache.clear()
        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True
        self.set_status(f"Background: {self.preview_background}")

    # ---------- color ----------
    def apply_hue_saturation_to_image(self, image, hue_degrees, saturation_percent, brightness_percent=100):
        image = image.convert("RGBA")
        alpha = image.getchannel("A")
        hsv = image.convert("RGB").convert("HSV")
        h, s, v = hsv.split()

        hue_shift = int((float(hue_degrees) / 360.0) * 255)
        h = h.point(lambda value: (value + hue_shift) % 256)
        sat_scale = max(0.0, float(saturation_percent) / 100.0)
        s = s.point(lambda value: max(0, min(255, int(value * sat_scale))))

        adjusted = Image.merge("HSV", (h, s, v)).convert("RGBA")
        brightness_scale = max(0.0, float(brightness_percent) / 100.0)
        adjusted_rgb = ImageEnhance.Brightness(adjusted.convert("RGB")).enhance(brightness_scale)
        adjusted = adjusted_rgb.convert("RGBA")
        adjusted.putalpha(alpha)
        return adjusted

    def make_color_wheel_image(self, size=160):
        try:
            import numpy as np
        except ImportError:
            image = Image.new("RGB", (size, size), (28, 28, 28))
            return image

        center = (size - 1) / 2.0
        y, x = np.ogrid[:size, :size]
        dx = x - center
        dy = y - center
        radius = np.sqrt(dx * dx + dy * dy)
        hue = ((np.arctan2(dy, dx) / (2 * np.pi)) + 1.0) % 1.0
        saturation = np.clip(radius / center, 0, 1)
        value = np.ones_like(hue)

        i = np.floor(hue * 6).astype(int)
        f = hue * 6 - i
        p = value * (1 - saturation)
        q = value * (1 - f * saturation)
        t = value * (1 - (1 - f) * saturation)

        rgb = np.zeros((size, size, 3), dtype=np.float32)
        masks = [i % 6 == n for n in range(6)]
        rgb[masks[0]] = np.stack([value, t, p], axis=-1)[masks[0]]
        rgb[masks[1]] = np.stack([q, value, p], axis=-1)[masks[1]]
        rgb[masks[2]] = np.stack([p, value, t], axis=-1)[masks[2]]
        rgb[masks[3]] = np.stack([p, q, value], axis=-1)[masks[3]]
        rgb[masks[4]] = np.stack([t, p, value], axis=-1)[masks[4]]
        rgb[masks[5]] = np.stack([value, p, q], axis=-1)[masks[5]]

        rgb[radius > center] = (0.11, 0.11, 0.11)
        return Image.fromarray((rgb * 255).astype("uint8"), "RGB")

    def color_match_image(self, source_image, reference_image):
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("Install numpy to use color matching")

        source = source_image.convert("RGBA")
        alpha = source.getchannel("A")
        src = np.asarray(source.convert("RGB"), dtype=np.float32)
        ref = np.asarray(reference_image.convert("RGB"), dtype=np.float32)

        src_mean = src.reshape(-1, 3).mean(axis=0)
        src_std = src.reshape(-1, 3).std(axis=0)
        ref_mean = ref.reshape(-1, 3).mean(axis=0)
        ref_std = ref.reshape(-1, 3).std(axis=0)

        matched = (src - src_mean) * (ref_std / np.maximum(src_std, 1.0)) + ref_mean
        matched = np.clip(matched, 0, 255).astype("uint8")
        result = Image.fromarray(matched, "RGB").convert("RGBA")
        result.putalpha(alpha)
        return result

    def histogram_match_channel(self, source, reference):
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("Install numpy to use color matching")

        source_shape = source.shape
        source = source.ravel()
        reference = reference.ravel()
        src_values, src_inverse, src_counts = np.unique(source, return_inverse=True, return_counts=True)
        ref_values, ref_counts = np.unique(reference, return_counts=True)
        src_quantiles = np.cumsum(src_counts).astype(np.float64)
        src_quantiles /= src_quantiles[-1]
        ref_quantiles = np.cumsum(ref_counts).astype(np.float64)
        ref_quantiles /= ref_quantiles[-1]
        matched = np.interp(src_quantiles, ref_quantiles, ref_values)
        return matched[src_inverse].reshape(source_shape)

    def histogram_match_image(self, source_image, reference_image):
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("Install numpy to use color matching")

        source = source_image.convert("RGBA")
        alpha = source.getchannel("A")
        src = np.asarray(source.convert("RGB"), dtype=np.uint8)
        ref = np.asarray(reference_image.convert("RGB"), dtype=np.uint8)
        matched = np.zeros_like(src, dtype=np.float32)
        for channel in range(3):
            matched[..., channel] = self.histogram_match_channel(src[..., channel], ref[..., channel])
        result = Image.fromarray(np.clip(matched, 0, 255).astype("uint8"), "RGB").convert("RGBA")
        result.putalpha(alpha)
        return result

    def covariance_match_image(self, source_image, reference_image):
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("Install numpy to use color matching")

        source = source_image.convert("RGBA")
        alpha = source.getchannel("A")
        src = np.asarray(source.convert("RGB"), dtype=np.float32)
        ref = np.asarray(reference_image.convert("RGB"), dtype=np.float32)
        src_flat = src.reshape(-1, 3)
        ref_flat = ref.reshape(-1, 3)
        src_mean = src_flat.mean(axis=0)
        ref_mean = ref_flat.mean(axis=0)
        src_cov = np.cov(src_flat, rowvar=False) + np.eye(3) * 1e-5
        ref_cov = np.cov(ref_flat, rowvar=False) + np.eye(3) * 1e-5

        src_vals, src_vecs = np.linalg.eigh(src_cov)
        ref_vals, ref_vecs = np.linalg.eigh(ref_cov)
        whiten = src_vecs @ np.diag(1.0 / np.sqrt(np.maximum(src_vals, 1e-5))) @ src_vecs.T
        colorize = ref_vecs @ np.diag(np.sqrt(np.maximum(ref_vals, 1e-5))) @ ref_vecs.T
        matched = (src_flat - src_mean) @ whiten @ colorize + ref_mean
        matched = matched.reshape(src.shape)
        result = Image.fromarray(np.clip(matched, 0, 255).astype("uint8"), "RGB").convert("RGBA")
        result.putalpha(alpha)
        return result

    def apply_color_match_method(self, source_image, reference_image, method=None):
        method = method or self.color_match_method
        if method == "Reinhard":
            return self.color_match_image(source_image, reference_image)
        if method == "HM":
            return self.histogram_match_image(source_image, reference_image)
        if method in ("MKL", "MVGD"):
            return self.covariance_match_image(source_image, reference_image)
        if method == "HM-MVGD-HM":
            first = self.histogram_match_image(source_image, reference_image)
            second = self.covariance_match_image(first, reference_image)
            return self.histogram_match_image(second, reference_image)
        if method == "HM-MKL-HM":
            first = self.histogram_match_image(source_image, reference_image)
            second = self.covariance_match_image(first, reference_image)
            return self.histogram_match_image(second, reference_image)
        return self.histogram_match_image(source_image, reference_image)

    def get_selected_reference_image(self):
        return self.open_image_copy(self.frame_paths[self.current_index], "RGB", "open selected reference frame")

    def set_color_reference_from_frame(self, index=None):
        if not self.frames:
            self.set_status("Open a video before setting a reference")
            return

        if index is None:
            index = self.current_index

        self.color_reference_image = self.open_image_copy(self.frame_paths[index], "RGB", "open color reference frame")
        if self.color_reference_image is None:
            return
        self.color_reference_label = f"Frame {index}"
        self.set_status(f"Color reference set from frame {index}")

    def match_frame_to_selected_reference(self, index=None):
        if not self.frames:
            return

        if index is None:
            index = self.current_index
        reference_index = self.current_index
        if index == reference_index:
            self.set_status("Selected frame is the color reference")
            return

        try:
            reference = self.get_selected_reference_image()
            if reference is None:
                return
            image = self.open_image_copy(self.frame_paths[index], "RGBA", "open frame for color match")
            if image is None:
                return
            matched = self.apply_color_match_method(image, reference)
            if not self.save_edited_frame(index, matched):
                return
            self.prime_caches_near_current()
            self.rebuild_timeline_metrics()
            self.set_status(f"Matched frame {index} to selected frame using {self.color_match_method}")
        except RuntimeError as exc:
            self.set_status(str(exc))

    def match_next_frame_to_selected_reference(self):
        if not self.frames:
            return
        target_index = self.current_index + 1 if self.current_index + 1 < len(self.frames) else self.current_index - 1
        if target_index < 0:
            self.set_status("No other frame to match")
            return
        self.match_frame_to_selected_reference(target_index)

    def blend_selected_with_adjacent_frames(self, prev_weight=None, current_weight=None, next_weight=None):
        if not self.frames:
            return

        prev_index = self.current_index - 1
        next_index = self.current_index + 1
        if prev_index < 0 and next_index >= len(self.frames):
            self.set_status("No adjacent frames to blend")
            return

        prev_weight = self.color_blend_prev_weight if prev_weight is None else float(prev_weight)
        current_weight = self.color_blend_current_weight if current_weight is None else float(current_weight)
        next_weight = self.color_blend_next_weight if next_weight is None else float(next_weight)
        if prev_index < 0:
            prev_weight = 0.0
        if next_index >= len(self.frames):
            next_weight = 0.0

        total_weight = prev_weight + current_weight + next_weight
        if total_weight <= 0:
            self.set_status("Blend weights must be above zero")
            return

        try:
            import numpy as np
        except ImportError:
            self.set_status("Install numpy to use adjacent blending")
            return

        current = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open current frame")
        if current is None:
            return
        alpha = current.getchannel("A")
        current_rgb = current.convert("RGB")
        accum = np.asarray(current_rgb, dtype=np.float32) * current_weight

        if prev_weight > 0:
            prev_reference = self.open_image_copy(self.frame_paths[prev_index], "RGB", "open previous frame")
            if prev_reference is None:
                return
            prev_matched = self.apply_color_match_method(current_rgb, prev_reference).convert("RGB")
            accum += np.asarray(prev_matched, dtype=np.float32) * prev_weight

        if next_weight > 0:
            next_reference = self.open_image_copy(self.frame_paths[next_index], "RGB", "open next frame")
            if next_reference is None:
                return
            next_matched = self.apply_color_match_method(current_rgb, next_reference).convert("RGB")
            accum += np.asarray(next_matched, dtype=np.float32) * next_weight

        blended = np.clip(accum / total_weight, 0, 255).astype("uint8")
        result = Image.fromarray(blended, "RGB").convert("RGBA")
        result.putalpha(alpha)
        if not self.save_edited_frame(self.current_index, result):
            return
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.set_status(f"Blended selected frame {prev_weight:.0f}/{current_weight:.0f}/{next_weight:.0f}")

    def match_video_to_selected_reference(self):
        if not self.frames:
            return

        reference_index = self.current_index
        reference = self.get_selected_reference_image()
        if reference is None:
            return
        self.loading_message = "Color matching video to selected frame..."
        self.force_redraw()
        try:
            for i, path in enumerate(self.frame_paths):
                if i == reference_index:
                    continue
                image = self.open_image_copy(path, "RGBA", "open frame for color match")
                if image is None:
                    self.loading_message = ""
                    return
                matched = self.apply_color_match_method(image, reference)
                if not self.save_image_retry(matched.convert("RGBA"), path, "save color matched frame"):
                    self.loading_message = ""
                    return
        except RuntimeError as exc:
            self.loading_message = ""
            self.set_status(str(exc))
            return

        self.invalidate_frame_cache()
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.loading_message = ""
        self.set_status(f"Matched video to frame {reference_index} using {self.color_match_method}")

    def match_frame_to_color_reference(self, index=None):
        self.match_frame_to_selected_reference(index)

    def match_video_to_color_reference(self):
        self.match_video_to_selected_reference()

    def hue_between_smaller_arc(self, hue_degrees, start_degrees, end_degrees):
        hue = hue_degrees % 360.0
        start = start_degrees % 360.0
        end = end_degrees % 360.0
        clockwise = (end - start) % 360.0
        if clockwise <= 180.0:
            return ((hue - start) % 360.0) <= clockwise
        return ((hue - end) % 360.0) <= (360.0 - clockwise)

    def build_color_range_region(self, image, hue_a, hue_b, sat_low, sat_high):
        try:
            import numpy as np
        except ImportError:
            self.set_status("Install numpy to use color range selection")
            return None

        hsv = image.convert("RGB").convert("HSV")
        data = np.asarray(hsv, dtype=np.float32)
        hue_degrees = data[..., 0] * (360.0 / 255.0)
        saturation = data[..., 1] * (200.0 / 255.0)
        low = min(float(sat_low), float(sat_high))
        high = max(float(sat_low), float(sat_high))
        hue_low = min(float(hue_a), float(hue_b)) % 360.0
        hue_high = max(float(hue_a), float(hue_b)) % 360.0
        if abs(hue_high - hue_low) < 0.0001:
            hue_tolerance = 360.0 / 255.0
            hue_delta = np.minimum((hue_degrees - hue_low) % 360.0, (hue_low - hue_degrees) % 360.0)
            hue_mask = hue_delta <= hue_tolerance
        else:
            hue_mask = (hue_degrees >= hue_low) & (hue_degrees <= hue_high)
        return hue_mask & (saturation >= low) & (saturation <= high)

    def apply_color_range_selection_to_frame(self, index, hue_a, hue_b, sat_low, sat_high, alpha_value):
        image = self.open_image_copy(self.frame_paths[index], "RGBA", "open color range frame")
        if image is None:
            return False
        try:
            region = self.build_color_range_region(image, hue_a, hue_b, sat_low, sat_high)
            if region is None:
                return False
            import numpy as np
            alpha = np.asarray(image.getchannel("A"), dtype=np.uint8).copy()
            alpha[region] = alpha_value
            image.putalpha(Image.fromarray(alpha, "L"))
            if not self.save_edited_frame(index, image):
                return False
            return True
        finally:
            image.close()

    def sample_frame_hue_saturation(self, image_pos):
        image = self.open_image_copy(self.frame_paths[self.current_index], "RGB", "sample color range pixel")
        if image is None:
            return None
        try:
            x, y = image_pos
            r, g, b = image.getpixel((x, y))
        finally:
            image.close()

        import colorsys
        hue, saturation, _value = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        return hue * 360.0, saturation * 200.0

    def open_color_range_tools(self):
        if not self.frames:
            self.set_status("Open a video before using color range")
            return

        if self.active_tool == "color_range" and self.color_range_popup is not None and self.color_range_popup.winfo_exists():
            self.color_range_popup.lift()
            return
        self.set_active_tool("color_range")

        popup = Toplevel(self.tk_root)
        popup.title("Remove By Color")
        popup.resizable(False, False)
        self.color_range_popup = popup

        main = Frame(popup, padx=14, pady=12)
        main.pack()

        wheel_image = self.make_color_wheel_image()
        wheel_photo = ImageTk.PhotoImage(wheel_image)
        wheel_label = Label(main, image=wheel_photo, cursor="crosshair")
        wheel_label.image = wheel_photo
        wheel_label.grid(row=0, column=0, rowspan=7, padx=(0, 14))

        hue_a_var = StringVar(value="0")
        hue_b_var = StringVar(value="40")
        status_var = StringVar(value="Left click sets low; right click sets high")

        Label(main, text="Low Hue").grid(row=1, column=1, sticky="w")
        Entry(main, textvariable=hue_a_var, width=8).grid(row=1, column=2, sticky="ew", pady=3)
        Label(main, text="High Hue").grid(row=2, column=1, sticky="w")
        Entry(main, textvariable=hue_b_var, width=8).grid(row=2, column=2, sticky="ew", pady=3)

        Label(main, text="Sat Low").grid(row=3, column=1, sticky="w")
        sat_low = Scale(main, from_=0, to=200, orient=HORIZONTAL, length=220, resolution=1)
        sat_low.set(0)
        sat_low.grid(row=3, column=2, sticky="ew")

        Label(main, text="Sat High").grid(row=4, column=1, sticky="w")
        sat_high = Scale(main, from_=0, to=200, orient=HORIZONTAL, length=220, resolution=1)
        sat_high.set(200)
        sat_high.grid(row=4, column=2, sticky="ew")

        Label(main, textvariable=status_var, anchor="w").grid(row=5, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        def values():
            return float(hue_a_var.get()), float(hue_b_var.get()), sat_low.get(), sat_high.get()

        def update_selection(combine_mode="replace"):
            try:
                hue_a, hue_b, low, high = values()
            except ValueError:
                status_var.set("Hue values must be numbers")
                return
            image = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open color range frame")
            if image is None:
                return
            try:
                region = self.build_color_range_region(image, hue_a, hue_b, low, high)
            finally:
                image.close()
            if region is None:
                return
            self.combine_selection_region(region, combine_mode)
            selected = int(region.sum()) if hasattr(region, "sum") else 0
            status_var.set(f"Selected {selected} matching pixels")

        def set_low_sample(hue, saturation=None):
            hue_a_var.set(f"{hue:.0f}")
            update_selection("replace")

        def set_high_sample(hue, saturation=None):
            hue_b_var.set(f"{hue:.0f}")
            update_selection("replace")

        def pick_from_wheel(event, high=False):
            import math

            size = 160
            center = (size - 1) / 2.0
            dx = event.x - center
            dy = event.y - center
            radius = (dx * dx + dy * dy) ** 0.5
            if radius > center:
                return
            hue = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
            if high:
                set_high_sample(hue)
            else:
                set_low_sample(hue)

        def sample_from_image(image_pos, high=False):
            sample = self.sample_frame_hue_saturation(image_pos)
            if sample is None:
                return
            hue, saturation = sample
            if high:
                set_high_sample(hue)
                self.set_status(f"Color range high {hue:.0f} hue / {saturation:.0f} sat")
            else:
                set_low_sample(hue)
                self.set_status(f"Color range low {hue:.0f} hue / {saturation:.0f} sat")

        def erase_current():
            try:
                hue_a, hue_b, low, high = values()
            except ValueError:
                status_var.set("Hue values must be numbers")
                return
            if self.apply_color_range_selection_to_frame(self.current_index, hue_a, hue_b, low, high, 0):
                self.prime_caches_near_current()
                self.rebuild_timeline_metrics()
                self.set_status("Erased color range on selected frame")

        def erase_all():
            try:
                hue_a, hue_b, low, high = values()
            except ValueError:
                status_var.set("Hue values must be numbers")
                return
            self.loading_message = "Erasing color range..."
            self.force_redraw()
            for i in range(len(self.frame_paths)):
                self.loading_message = f"Erasing color range... {i + 1}/{len(self.frame_paths)}"
                if i % 5 == 0:
                    self.force_redraw()
                if not self.apply_color_range_selection_to_frame(i, hue_a, hue_b, low, high, 0):
                    self.loading_message = ""
                    return
            self.loading_message = ""
            self.invalidate_frame_cache()
            self.prime_caches_near_current()
            self.rebuild_timeline_metrics()
            self.set_status("Erased color range on all frames", 5000)

        def close_popup():
            self.close_color_range_tools()

        sat_low.configure(command=lambda _value: update_selection("replace"))
        sat_high.configure(command=lambda _value: update_selection("replace"))
        hue_a_var.trace_add("write", lambda *_args: update_selection("replace"))
        hue_b_var.trace_add("write", lambda *_args: update_selection("replace"))
        wheel_label.bind("<Button-1>", lambda event: pick_from_wheel(event, high=False))
        wheel_label.bind("<B1-Motion>", lambda event: pick_from_wheel(event, high=False))
        wheel_label.bind("<Button-3>", lambda event: pick_from_wheel(event, high=True))
        wheel_label.bind("<B3-Motion>", lambda event: pick_from_wheel(event, high=True))
        self.color_range_image_sampler = sample_from_image

        buttons = Frame(main)
        buttons.grid(row=6, column=1, columnspan=2, sticky="e", pady=(12, 0))
        Button(buttons, text="Preview Selection", command=lambda: update_selection("replace")).pack(side="left", padx=(0, 8))
        Button(buttons, text="Add Selection", command=lambda: update_selection("add")).pack(side="left", padx=(0, 8))
        Button(buttons, text="Subtract Selection", command=lambda: update_selection("subtract")).pack(side="left", padx=(0, 8))
        Button(buttons, text="Erase Current", command=erase_current).pack(side="left", padx=(0, 8))
        Button(buttons, text="Erase All", command=erase_all).pack(side="left", padx=(0, 8))
        Button(buttons, text="Close", command=close_popup).pack(side="left")

        popup.protocol("WM_DELETE_WINDOW", close_popup)
        popup.bind("<Escape>", lambda _event: close_popup())
        update_selection("replace")

    def open_color_tools(self):
        if not self.frames:
            self.set_status("Open a video before using color tools")
            return

        if self.active_tool == "color" and self.color_popup is not None and self.color_popup.winfo_exists():
            self.color_popup.lift()
            return
        self.set_active_tool("color")

        popup = Toplevel(self.tk_root)
        popup.title("Color Match")
        popup.resizable(False, False)
        self.color_popup = popup

        base_image = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open color tool frame")
        if base_image is None:
            self.close_color_tools()
            return

        main = Frame(popup, padx=14, pady=12)
        main.pack()

        preview_frame = Frame(main)
        preview_frame.grid(row=0, column=0, columnspan=4, sticky="nsew")

        wheel_image = self.make_color_wheel_image()
        self.color_wheel_photo = ImageTk.PhotoImage(wheel_image)
        wheel_label = Label(preview_frame, image=self.color_wheel_photo, cursor="crosshair")
        wheel_label.grid(row=0, column=0, padx=(0, 14))

        prev_preview = Label(preview_frame, bg="black")
        prev_preview.grid(row=0, column=1, padx=(0, 8))
        frame_preview = Label(preview_frame, bg="black")
        frame_preview.grid(row=0, column=2, padx=(0, 8))
        next_preview = Label(preview_frame, bg="black")
        next_preview.grid(row=0, column=3)
        ref_var = StringVar(value=f"Selected frame {self.current_index} is the reference")
        Label(main, textvariable=ref_var, anchor="w").grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        Label(main, text="Method").grid(row=2, column=0, sticky="w", pady=(10, 0))
        method_var = StringVar(value=self.color_match_method)
        method_menu = OptionMenu(main, method_var, "HM", "Reinhard", "MKL", "MVGD", "HM-MVGD-HM", "HM-MKL-HM")
        method_menu.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(10, 0))

        Label(main, text="Hue").grid(row=3, column=0, sticky="w", pady=(10, 0))
        hue_scale = Scale(main, from_=-180, to=180, orient=HORIZONTAL, length=320, resolution=1)
        hue_scale.grid(row=3, column=1, columnspan=3, sticky="ew", pady=(10, 0))

        Label(main, text="Saturation").grid(row=4, column=0, sticky="w")
        sat_scale = Scale(main, from_=0, to=200, orient=HORIZONTAL, length=320, resolution=1)
        sat_scale.set(100)
        sat_scale.grid(row=4, column=1, columnspan=3, sticky="ew")

        Label(main, text="Brightness").grid(row=5, column=0, sticky="w")
        brightness_scale = Scale(main, from_=0, to=200, orient=HORIZONTAL, length=320, resolution=1)
        brightness_scale.set(100)
        brightness_scale.grid(row=5, column=1, columnspan=3, sticky="ew")

        weights_frame = Frame(main)
        weights_frame.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        prev_weight_var = StringVar(value=f"{self.color_blend_prev_weight:g}")
        current_weight_var = StringVar(value=f"{self.color_blend_current_weight:g}")
        next_weight_var = StringVar(value=f"{self.color_blend_next_weight:g}")
        Label(weights_frame, text="Blend Prev").pack(side="left")
        Entry(weights_frame, textvariable=prev_weight_var, width=5).pack(side="left", padx=(4, 10))
        Label(weights_frame, text="Current").pack(side="left")
        Entry(weights_frame, textvariable=current_weight_var, width=5).pack(side="left", padx=(4, 10))
        Label(weights_frame, text="Next").pack(side="left")
        Entry(weights_frame, textvariable=next_weight_var, width=5).pack(side="left", padx=(4, 0))

        preview_state = {"photo": None}

        def make_adjusted():
            return self.apply_hue_saturation_to_image(base_image, hue_scale.get(), sat_scale.get(), brightness_scale.get())

        def make_preview_photo(image, size=(220, 160)):
            preview = image.convert("RGBA").copy()
            preview.thumbnail(size, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(preview)

        def update_color_preview(_value=None):
            adjusted = make_adjusted()
            photo = make_preview_photo(adjusted, (300, 220))
            frame_preview.configure(image=photo)
            frame_preview.image = photo
            preview_state["photo"] = photo

        def update_reference_previews():
            prev_index = self.current_index - 1
            next_index = self.current_index + 1
            if prev_index >= 0:
                image = self.open_image_copy(self.frame_paths[prev_index], "RGBA", "open previous color reference")
                if image is None:
                    return
                prev_photo = make_preview_photo(image)
                prev_preview.configure(image=prev_photo, text="", width=0, height=0)
                prev_preview.image = prev_photo
            else:
                prev_preview.configure(image="", text="No previous", width=20, height=8, fg="white")
                prev_preview.image = None

            if next_index < len(self.frame_paths):
                image = self.open_image_copy(self.frame_paths[next_index], "RGBA", "open next color reference")
                if image is None:
                    return
                next_photo = make_preview_photo(image)
                next_preview.configure(image=next_photo, text="", width=0, height=0)
                next_preview.image = next_photo
            else:
                next_preview.configure(image="", text="No next", width=20, height=8, fg="white")
                next_preview.image = None

        def apply_to_current():
            adjusted = make_adjusted()
            if not self.save_edited_frame(self.current_index, adjusted):
                return
            self.prime_caches_near_current()
            self.rebuild_timeline_metrics()
            ref_var.set(f"Selected frame {self.current_index} is the reference")
            self.set_status(f"Applied color adjustment to selected frame {self.current_index}")

        def blend_adjacent():
            self.color_match_method = method_var.get()
            try:
                self.color_blend_prev_weight = float(prev_weight_var.get())
                self.color_blend_current_weight = float(current_weight_var.get())
                self.color_blend_next_weight = float(next_weight_var.get())
            except ValueError:
                self.set_status("Blend weights must be numbers")
                return
            self.blend_selected_with_adjacent_frames()

        def match_all():
            self.color_match_method = method_var.get()
            self.match_video_to_selected_reference()

        def update_method(*_args):
            self.color_match_method = method_var.get()

        def refresh_for_selected_frame():
            nonlocal base_image
            image = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open color tool frame")
            if image is None:
                return
            base_image = image
            hue_scale.set(0)
            sat_scale.set(100)
            brightness_scale.set(100)
            ref_var.set(f"Selected frame {self.current_index} is the reference")
            update_reference_previews()
            update_color_preview()

        def pick_from_wheel(event):
            import math

            size = 160
            center = (size - 1) / 2.0
            dx = event.x - center
            dy = event.y - center
            radius = (dx * dx + dy * dy) ** 0.5
            if radius > center:
                return
            hue_degrees = math.degrees(math.atan2(dy, dx))
            saturation = int(max(0, min(200, (radius / center) * 200)))
            hue_scale.set(int(hue_degrees))
            sat_scale.set(saturation)
            update_color_preview()

        def close_popup():
            self.close_color_tools()

        hue_scale.configure(command=update_color_preview)
        sat_scale.configure(command=update_color_preview)
        brightness_scale.configure(command=update_color_preview)
        method_var.trace_add("write", update_method)
        wheel_label.bind("<Button-1>", pick_from_wheel)
        wheel_label.bind("<B1-Motion>", pick_from_wheel)

        buttons = Frame(main)
        buttons.grid(row=7, column=0, columnspan=4, sticky="e", pady=(12, 0))
        Button(buttons, text="Apply To Selected", command=apply_to_current).pack(side="left", padx=(0, 8))
        Button(buttons, text="Blend Adjacent", command=blend_adjacent).pack(side="left", padx=(0, 8))
        Button(buttons, text="Match Whole Video", command=match_all).pack(side="left", padx=(0, 8))
        Button(buttons, text="Close", command=close_popup).pack(side="left")

        popup.protocol("WM_DELETE_WINDOW", close_popup)
        popup.bind("<Escape>", lambda _event: close_popup())
        self.color_tool_refresh = refresh_for_selected_frame
        update_reference_previews()
        update_color_preview()

    # ---------- background / mask ----------
    def toggle_mask_edit_mode(self):
        if self.mask_edit_mode:
            self.mask_edit_mode = False
            self.mask_dragging = False
            self.clear_active_tool("mask")
            self.set_status("Mask edit off")
            return

        self.set_active_tool("mask")
        self.mask_edit_mode = True
        self.mask_dragging = False
        self.set_status("Mask edit on")

    def set_mask_restore_mode(self):
        self.mask_paint_mode = "restore"
        self.set_status("Mask brush adds to selection")

    def set_mask_erase_mode(self):
        self.mask_paint_mode = "erase"
        self.set_status("Mask brush removes from selection")

    def toggle_wand_mode(self):
        if self.wand_mode:
            self.wand_mode = False
            self.wand_dragging = False
            self.wand_start_pos = None
            self.wand_drag_base = None
            self.clear_active_tool("wand")
            self.set_status("Wand select off")
            return

        self.set_active_tool("wand")
        self.wand_mode = True
        self.wand_dragging = False
        if self.frames:
            try:
                self.get_wand_zone_cache(self.current_index)
            except RuntimeError as exc:
                self.set_status(str(exc))
                self.wand_mode = False
                self.clear_active_tool("wand")
                self.loading_message = ""
                return
        self.set_status("Wand select on")

    def clear_wand_selection(self):
        self.wand_selection = None
        self.wand_dragging = False
        self.set_status("Selection cleared")

    def combine_selection_region(self, region, combine_mode="replace"):
        if region is None:
            return
        base = self.wand_selection
        if combine_mode == "add" and base is not None:
            self.wand_selection = base | region
        elif combine_mode == "subtract" and base is not None:
            self.wand_selection = base & ~region
        elif combine_mode == "subtract":
            self.wand_selection = None
        else:
            self.wand_selection = region

    def brush_selection_at(self, mouse, combine_mode="add"):
        pos = self.preview_to_image_pos(mouse)
        if pos is None:
            return

        try:
            import numpy as np
        except ImportError:
            self.set_status("Install numpy to use mask selection brush")
            return

        full = self.load_full_surface(self.current_index)
        img_w, img_h = full.get_size()
        x, y = pos
        yy, xx = np.ogrid[:img_h, :img_w]
        radius = max(1, int(self.mask_brush_size))
        region = ((xx - x) * (xx - x) + (yy - y) * (yy - y)) <= radius * radius
        self.combine_selection_region(region, combine_mode)
        self.set_status("Added to selection" if combine_mode == "add" else "Removed from selection")

    def adjust_mask_brush_size(self, delta):
        sizes = list(range(1, 11)) + [12, 15, 20, 25, 32, 40, 50, 64, 80, 100, 128, 160, 200]
        current = min(range(len(sizes)), key=lambda i: abs(sizes[i] - self.mask_brush_size))
        current = max(0, min(len(sizes) - 1, current + delta))
        self.mask_brush_size = sizes[current]
        self.set_status(f"Mask brush {self.mask_brush_size}px")

    def preview_to_image_pos(self, mouse):
        if not self.frames:
            return None

        rect = self.get_preview_rect()
        if not rect.collidepoint(mouse):
            return None

        full = self.load_full_surface(self.current_index)
        img_w, img_h = full.get_size()
        fit_scale = min(rect.w / img_w, rect.h / img_h)
        scale = max(0.05, fit_scale * self.preview_zoom)
        draw_w = max(1, int(img_w * scale))
        draw_h = max(1, int(img_h * scale))
        draw_x = rect.x + (rect.w - draw_w) // 2 + int(self.preview_offset[0])
        draw_y = rect.y + (rect.h - draw_h) // 2 + int(self.preview_offset[1])

        x = int((mouse[0] - draw_x) / scale)
        y = int((mouse[1] - draw_y) / scale)
        if x < 0 or y < 0 or x >= img_w or y >= img_h:
            return None
        return x, y

    def paint_mask_at(self, mouse):
        combine_mode = "add" if self.mask_paint_mode == "restore" else "subtract"
        self.brush_selection_at(mouse, combine_mode)

    def get_wand_zone_cache(self, index):
        with self.wand_zone_lock:
            cached = self.wand_zone_cache.get(index)
        if cached is not None:
            return cached

        self.loading_message = "Preparing wand zones..."
        self.force_redraw()
        try:
            return self.build_wand_zone_cache(index)
        finally:
            self.loading_message = ""

    def build_wand_zone_cache(self, index):
        with self.wand_zone_lock:
            cached = self.wand_zone_cache.get(index)
        if cached is not None:
            return cached

        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("Install numpy to use wand selection")

        image = self.open_image_copy(self.frame_paths[index], "RGB", "open frame for wand zones")
        if image is None:
            raise RuntimeError("Could not open frame for wand zones")
        rgb = np.asarray(image, dtype=np.uint8)

        labels, component_colors = self.build_wand_components(rgb, np)
        component_id = len(component_colors)
        adjacency = [set() for _ in range(component_id)]
        horizontal_a = labels[:, :-1]
        horizontal_b = labels[:, 1:]
        vertical_a = labels[:-1, :]
        vertical_b = labels[1:, :]
        for a, b in zip(horizontal_a[horizontal_a != horizontal_b], horizontal_b[horizontal_a != horizontal_b]):
            adjacency[int(a)].add(int(b))
            adjacency[int(b)].add(int(a))
        for a, b in zip(vertical_a[vertical_a != vertical_b], vertical_b[vertical_a != vertical_b]):
            adjacency[int(a)].add(int(b))
            adjacency[int(b)].add(int(a))

        cached = {
            "labels": labels,
            "colors": np.asarray(component_colors, dtype=np.float32),
            "adjacency": [tuple(item) for item in adjacency],
        }
        with self.wand_zone_lock:
            self.wand_zone_cache[index] = cached
        return cached

    def build_wand_components(self, rgb, np):
        try:
            from skimage.measure import label
        except ImportError:
            return self.build_wand_components_python(rgb, np)

        quantized = (rgb // 16).astype(np.uint16)
        color_key = (
            (quantized[..., 0] << 8)
            | (quantized[..., 1] << 4)
            | quantized[..., 2]
        )
        labels = label(color_key, background=-1, connectivity=1).astype(np.int32) - 1
        component_count = int(labels.max()) + 1
        flat_labels = labels.ravel()
        flat_rgb = rgb.reshape(-1, 3).astype(np.float64)
        counts = np.bincount(flat_labels, minlength=component_count)
        component_colors = []
        for channel in range(3):
            sums = np.bincount(flat_labels, weights=flat_rgb[:, channel], minlength=component_count)
            component_colors.append(sums / np.maximum(counts, 1))
        component_colors = np.stack(component_colors, axis=1)
        return labels, component_colors

    def build_wand_components_python(self, rgb, np):
        h, w = rgb.shape[:2]
        quantized = (rgb // 16).astype(np.uint16)
        color_key = (
            (quantized[..., 0] << 8)
            | (quantized[..., 1] << 4)
            | quantized[..., 2]
        )
        labels = np.full((h, w), -1, dtype=np.int32)
        component_colors = []
        component_counts = []
        stack = []
        component_id = 0

        for y in range(h):
            for x in range(w):
                if labels[y, x] != -1:
                    continue
                key = color_key[y, x]
                labels[y, x] = component_id
                stack.append((x, y))
                total = np.zeros(3, dtype=np.float64)
                count = 0

                while stack:
                    px, py = stack.pop()
                    total += rgb[py, px]
                    count += 1
                    nx = px + 1
                    if nx < w and labels[py, nx] == -1 and color_key[py, nx] == key:
                        labels[py, nx] = component_id
                        stack.append((nx, py))
                    nx = px - 1
                    if nx >= 0 and labels[py, nx] == -1 and color_key[py, nx] == key:
                        labels[py, nx] = component_id
                        stack.append((nx, py))
                    ny = py + 1
                    if ny < h and labels[ny, px] == -1 and color_key[ny, px] == key:
                        labels[ny, px] = component_id
                        stack.append((px, ny))
                    ny = py - 1
                    if ny >= 0 and labels[ny, px] == -1 and color_key[ny, px] == key:
                        labels[ny, px] = component_id
                        stack.append((px, ny))

                component_colors.append(total / max(1, count))
                component_counts.append(count)
                component_id += 1
        return labels, component_colors

    def get_wand_preload_indexes(self):
        if not self.frames:
            return []
        indexes = [self.current_index]
        for offset in range(1, 4):
            left = self.current_index - offset
            right = self.current_index + offset
            if right < len(self.frames):
                indexes.append(right)
            if left >= 0:
                indexes.append(left)
        return indexes

    def schedule_wand_zone_preload(self):
        if not self.frames:
            return
        with self.wand_zone_lock:
            self.wand_preload_targets = self.get_wand_preload_indexes()
            if self.wand_preload_running:
                return
            self.wand_preload_running = True

        self.wand_preload_thread = threading.Thread(target=self.wand_zone_preload_worker, daemon=True)
        self.wand_preload_thread.start()

    def wand_zone_preload_worker(self):
        while True:
            with self.wand_zone_lock:
                while self.wand_preload_targets:
                    index = self.wand_preload_targets.pop(0)
                    if index not in self.wand_zone_cache:
                        break
                else:
                    self.wand_preload_running = False
                    return

            try:
                if 0 <= index < len(self.frame_paths):
                    self.build_wand_zone_cache(index)
            except Exception:
                pass

    def build_wand_region(self, image_pos, tolerance):
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("Install numpy to use wand selection")

        cache = self.get_wand_zone_cache(self.current_index)
        labels = cache["labels"]
        colors = cache["colors"]
        adjacency = cache["adjacency"]
        h, w = labels.shape
        start_x, start_y = image_pos
        if start_x < 0 or start_y < 0 or start_x >= w or start_y >= h:
            return None

        start_label = int(labels[start_y, start_x])
        target = colors[start_label]
        selected_components = set()
        visited = set()
        stack = [start_label]
        max_distance = float(tolerance)

        while stack:
            component = stack.pop()
            if component in visited:
                continue
            visited.add(component)
            distance = float(np.linalg.norm(colors[component] - target))
            if distance > max_distance:
                continue
            selected_components.add(component)
            stack.extend(adjacency[component])

        if not selected_components:
            return None
        return np.isin(labels, list(selected_components))

    def update_wand_selection(self, image_pos, combine_mode, tolerance):
        try:
            region = self.build_wand_region(image_pos, tolerance)
        except RuntimeError as exc:
            self.set_status(str(exc))
            return
        if region is None:
            return

        base = self.wand_drag_base if self.wand_drag_base is not None else self.wand_selection
        if combine_mode == "add" and base is not None:
            self.wand_selection = base | region
        elif combine_mode == "subtract" and base is not None:
            self.wand_selection = base & ~region
        else:
            self.wand_selection = region
        self.set_status(f"Wand tolerance {self.wand_tolerance}")

    def apply_wand_selection_to_alpha(self, alpha_value):
        if not self.frames or self.wand_selection is None:
            self.set_status("No wand selection")
            return

        try:
            import numpy as np
        except ImportError:
            self.set_status("Install numpy to use wand selection")
            return

        image = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open frame for wand edit")
        if image is None:
            return
        try:
            alpha = np.asarray(image.getchannel("A"), dtype=np.uint8).copy()
            if alpha.shape != self.wand_selection.shape:
                self.set_status("Selection size does not match frame")
                return
            alpha[self.wand_selection] = alpha_value
            image.putalpha(Image.fromarray(alpha, "L"))
            if not self.save_edited_frame(self.current_index, image):
                return
            self.prime_caches_near_current()
            self.rebuild_timeline_metrics()
            verb = "Restored" if alpha_value else "Erased"
            self.set_status(f"{verb} selected area")
        finally:
            image.close()

    def clear_current_mask(self):
        if not self.frames:
            return
        image = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open current mask")
        if image is None:
            return
        try:
            image.putalpha(0)
            if not self.save_edited_frame(self.current_index, image):
                return
            self.set_status("Erased current frame mask")
        finally:
            image.close()

    def fill_current_mask(self):
        if not self.frames:
            return
        image = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open current mask")
        if image is None:
            return
        try:
            image.putalpha(255)
            if not self.save_edited_frame(self.current_index, image):
                return
            self.set_status("Filled current frame mask")
        finally:
            image.close()

    def keep_largest_mask_component(self, mask, np):
        h, w = mask.shape
        visited = np.zeros_like(mask, dtype=bool)
        best_pixels = []
        for y in range(h):
            for x in range(w):
                if not mask[y, x] or visited[y, x]:
                    continue
                stack = [(x, y)]
                visited[y, x] = True
                pixels = []
                while stack:
                    px, py = stack.pop()
                    pixels.append((px, py))
                    for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                        if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((nx, ny))
                if len(pixels) > len(best_pixels):
                    best_pixels = pixels

        result = np.zeros_like(mask, dtype=bool)
        for x, y in best_pixels:
            result[y, x] = True
        return result

    def flood_exterior_mask(self, solid, np):
        h, w = solid.shape
        exterior = np.zeros_like(solid, dtype=bool)
        stack = []

        for x in range(w):
            if not solid[0, x]:
                stack.append((x, 0))
                exterior[0, x] = True
            if not solid[h - 1, x] and not exterior[h - 1, x]:
                stack.append((x, h - 1))
                exterior[h - 1, x] = True
        for y in range(h):
            if not solid[y, 0] and not exterior[y, 0]:
                stack.append((0, y))
                exterior[y, 0] = True
            if not solid[y, w - 1] and not exterior[y, w - 1]:
                stack.append((w - 1, y))
                exterior[y, w - 1] = True

        while stack:
            x, y = stack.pop()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h and not solid[ny, nx] and not exterior[ny, nx]:
                    exterior[ny, nx] = True
                    stack.append((nx, ny))
        return exterior

    def dilate_mask(self, mask, steps):
        result = mask.copy()
        for _ in range(steps):
            grown = result.copy()
            grown[1:, :] |= result[:-1, :]
            grown[:-1, :] |= result[1:, :]
            grown[:, 1:] |= result[:, :-1]
            grown[:, :-1] |= result[:, 1:]
            result = grown
        return result

    def erode_mask(self, mask, steps):
        result = mask.copy()
        for _ in range(steps):
            eroded = result.copy()
            eroded[1:, :] &= result[:-1, :]
            eroded[:-1, :] &= result[1:, :]
            eroded[:, 1:] &= result[:, :-1]
            eroded[:, :-1] &= result[:, 1:]
            eroded[0, :] = False
            eroded[-1, :] = False
            eroded[:, 0] = False
            eroded[:, -1] = False
            result = eroded
        return result

    def build_magic_outline_regions(self, alpha):
        try:
            import numpy as np
        except ImportError:
            self.set_status("Install numpy to use magic outline")
            return None

        alpha_array = np.asarray(alpha, dtype=np.uint8)
        solid = alpha_array >= 204
        if solid.shape[0] < 3 or solid.shape[1] < 3:
            return None

        silhouette = self.keep_largest_mask_component(solid, np)
        grown = self.dilate_mask(silhouette, 1)
        shrunk = self.erode_mask(silhouette, 1)
        outline = grown & ~shrunk
        outer = outline & ~silhouette
        inner = outline & silhouette

        outside = self.dilate_mask(grown, 1) & ~grown
        outside[0, :] = False
        outside[-1, :] = False
        outside[:, 0] = False
        outside[:, -1] = False

        outer[0, :] = False
        outer[-1, :] = False
        outer[:, 0] = False
        outer[:, -1] = False
        inner[0, :] = False
        inner[-1, :] = False
        inner[:, 0] = False
        inner[:, -1] = False
        return {
            "outside": outside,
            "outer": outer,
            "inner": inner,
        }

    def apply_magic_outline_to_frame(self, index):
        image = self.open_image_copy(self.frame_paths[index], "RGBA", "open frame for magic outline")
        if image is None:
            return False
        try:
            import numpy as np
            regions = self.build_magic_outline_regions(image.getchannel("A"))
            if regions is None:
                return False
            pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
            outside = regions["outside"]
            outer = regions["outer"]
            inner = regions["inner"]
            outline = outer | inner
            pixels[outside, 3] = 0
            pixels[outline, 0] = 10
            pixels[outline, 1] = 10
            pixels[outline, 2] = 10
            pixels[outer, 3] = 191
            pixels[inner, 3] = 255
            result = Image.fromarray(pixels, "RGBA")
            if not self.save_edited_frame(index, result):
                return False
            return True
        finally:
            image.close()

    def clear_magic_outline_from_frame(self, index):
        image = self.open_image_copy(self.frame_paths[index], "RGBA", "open frame for clearing magic outline")
        if image is None:
            return False
        try:
            import numpy as np
            regions = self.build_magic_outline_regions(image.getchannel("A"))
            if regions is None:
                return False
            pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
            dark = (
                (pixels[..., 0] <= 18)
                & (pixels[..., 1] <= 18)
                & (pixels[..., 2] <= 18)
                & (pixels[..., 3] > 0)
            )
            outline = regions["outer"] | regions["inner"]
            clear_pixels = dark & outline
            if not clear_pixels.any():
                return True
            pixels[clear_pixels, 3] = 0
            result = Image.fromarray(pixels, "RGBA")
            if not self.save_edited_frame(index, result):
                return False
            return True
        finally:
            image.close()

    def magic_outline_current_frame(self):
        if not self.frames:
            return
        if self.apply_magic_outline_to_frame(self.current_index):
            self.prime_caches_near_current()
            self.rebuild_timeline_metrics()
            self.set_status("Added magic outline")

    def magic_outline_whole_video(self):
        if not self.frames:
            return
        self.loading_message = "Adding magic outline..."
        self.force_redraw()
        for i in range(len(self.frame_paths)):
            self.loading_message = f"Adding magic outline... {i + 1}/{len(self.frame_paths)}"
            if i % 5 == 0:
                self.force_redraw()
            if not self.apply_magic_outline_to_frame(i):
                self.loading_message = ""
                return
        self.loading_message = ""
        self.invalidate_frame_cache()
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.set_status("Added magic outline to all frames", 5000)

    def clear_magic_outline_current_frame(self):
        if not self.frames:
            return
        if self.clear_magic_outline_from_frame(self.current_index):
            self.prime_caches_near_current()
            self.rebuild_timeline_metrics()
            self.set_status("Cleared magic outline")

    def clear_magic_outline_whole_video(self):
        if not self.frames:
            return
        self.loading_message = "Clearing magic outline..."
        self.force_redraw()
        for i in range(len(self.frame_paths)):
            self.loading_message = f"Clearing magic outline... {i + 1}/{len(self.frame_paths)}"
            if i % 5 == 0:
                self.force_redraw()
            if not self.clear_magic_outline_from_frame(i):
                self.loading_message = ""
                return
        self.loading_message = ""
        self.invalidate_frame_cache()
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.set_status("Cleared magic outline from all frames", 5000)

    def open_magic_outline_tools(self):
        if not self.frames:
            self.set_status("Open a video before using magic outline")
            return
        if self.active_tool == "magic_outline" and self.magic_outline_popup is not None and self.magic_outline_popup.winfo_exists():
            self.magic_outline_popup.lift()
            return
        self.set_active_tool("magic_outline")

        popup = Toplevel(self.tk_root)
        popup.title("Magic Outline")
        popup.resizable(False, False)
        self.magic_outline_popup = popup

        main = Frame(popup, padx=14, pady=12)
        main.pack()
        Label(main, text="Add or clear the black alpha outline.").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        Button(main, text="Add Current", command=self.magic_outline_current_frame, width=18).grid(row=1, column=0, padx=(0, 8), pady=4)
        Button(main, text="Clear Current", command=self.clear_magic_outline_current_frame, width=18).grid(row=1, column=1, pady=4)
        Button(main, text="Add Whole Video", command=self.magic_outline_whole_video, width=18).grid(row=2, column=0, padx=(0, 8), pady=4)
        Button(main, text="Clear Whole Video", command=self.clear_magic_outline_whole_video, width=18).grid(row=2, column=1, pady=4)

        def close_popup():
            self.close_magic_outline_tools()

        Button(main, text="Close", command=close_popup).grid(row=3, column=1, sticky="e", pady=(12, 0))
        popup.protocol("WM_DELETE_WINDOW", close_popup)
        popup.bind("<Escape>", lambda _event: close_popup())

    def remove_background_from_frame(self, index):
        try:
            rembg_module = importlib.import_module("rembg")
            remove = rembg_module.remove
            new_session = rembg_module.new_session
        except (ImportError, SystemExit):
            raise RuntimeError("Install rembg with CPU or GPU support to use background removal")

        session = self.rembg_sessions.get(self.rembg_model)
        if session is None:
            session = new_session(self.rembg_model)
            self.rembg_sessions[self.rembg_model] = session

        original = self.open_image_copy(self.frame_paths[index], "RGBA", "open frame for background removal")
        if original is None:
            raise RuntimeError("Could not open frame for background removal")
        result = remove(
            original,
            session=session,
            alpha_matting=self.rembg_alpha_matting,
            alpha_matting_foreground_threshold=self.rembg_fg_threshold,
            alpha_matting_background_threshold=self.rembg_bg_threshold,
            alpha_matting_erode_size=self.rembg_erode_size,
        )
        if isinstance(result, Image.Image):
            removed = result.convert("RGBA")
        else:
            removed = Image.open(io.BytesIO(result)).convert("RGBA")

        original.putalpha(removed.getchannel("A"))
        if not self.save_image_retry(original, self.frame_paths[index], "save background removal result"):
            raise RuntimeError("Could not save background removal result")

    def remove_background_current_frame(self):
        if not self.frames:
            return
        self.loading_message = "Removing background... please wait"
        self.set_status("Removing background; this can take a while", 5000)
        self.force_redraw()
        try:
            self.remove_background_from_frame(self.current_index)
        except Exception as exc:
            self.loading_message = ""
            self.set_status(str(exc))
            return
        self.loading_message = ""
        self.invalidate_frame_cache(self.current_index)
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.set_status("Removed background; enable Mask Edit to restore areas", 4000)

    def remove_background_whole_video(self):
        if not self.frames:
            return
        self.loading_message = "Removing backgrounds... please wait"
        self.set_status("Removing backgrounds; this can take a while", 5000)
        self.force_redraw()
        try:
            for i in range(len(self.frames)):
                self.loading_message = f"Removing backgrounds... {i + 1}/{len(self.frames)}"
                self.force_redraw()
                self.remove_background_from_frame(i)
        except Exception as exc:
            self.loading_message = ""
            self.set_status(str(exc))
            return
        self.loading_message = ""
        self.invalidate_frame_cache()
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.set_status("Removed backgrounds; enable Mask Edit to restore areas", 4000)

    def open_rembg_settings(self):
        if self.active_tool == "rembg_settings" and self.rembg_settings_popup is not None and self.rembg_settings_popup.winfo_exists():
            self.rembg_settings_popup.lift()
            return
        self.set_active_tool("rembg_settings")

        popup = Toplevel(self.tk_root)
        popup.title("Background Removal Settings")
        popup.resizable(False, False)
        self.rembg_settings_popup = popup

        main = Frame(popup, padx=14, pady=12)
        main.pack()

        model_var = StringVar(value=self.rembg_model)
        matting_var = StringVar(value="On" if self.rembg_alpha_matting else "Off")
        fg_var = StringVar(value=str(self.rembg_fg_threshold))
        bg_var = StringVar(value=str(self.rembg_bg_threshold))
        erode_var = StringVar(value=str(self.rembg_erode_size))
        error_var = StringVar(value="")

        Label(main, text="Model").grid(row=0, column=0, sticky="w", pady=4)
        OptionMenu(
            main,
            model_var,
            "isnet-anime",
            "isnet-general-use",
            "birefnet-general",
            "birefnet-general-lite",
            "u2net",
            "u2netp",
            "silueta",
        ).grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)

        Label(main, text="Alpha Matting").grid(row=1, column=0, sticky="w", pady=4)
        OptionMenu(main, matting_var, "On", "Off").grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)

        def add_entry(row, label, variable):
            Label(main, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = Entry(main, textvariable=variable, width=12)
            entry.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
            return entry

        add_entry(2, "Foreground Threshold", fg_var)
        add_entry(3, "Background Threshold", bg_var)
        add_entry(4, "Erode Size", erode_var)
        Label(main, textvariable=error_var, fg="red").grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))

        buttons = Frame(main)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))

        def close_popup():
            self.close_rembg_settings()

        def apply_settings():
            try:
                fg = int(fg_var.get())
                bg = int(bg_var.get())
                erode = int(erode_var.get())
            except ValueError:
                error_var.set("Thresholds and erode size must be whole numbers.")
                return

            if not (0 <= bg <= 255 and 0 <= fg <= 255 and erode >= 0):
                error_var.set("Thresholds must be 0-255; erode size must be 0+.")
                return

            old_model = self.rembg_model
            self.rembg_model = model_var.get()
            self.rembg_alpha_matting = matting_var.get() == "On"
            self.rembg_fg_threshold = fg
            self.rembg_bg_threshold = bg
            self.rembg_erode_size = erode
            if old_model != self.rembg_model:
                self.rembg_sessions.pop(old_model, None)
            self.set_status(f"RMBG: {self.rembg_model}, matting {matting_var.get()}")
            close_popup()

        Button(buttons, text="Cancel", command=close_popup).pack(side="right", padx=(8, 0))
        Button(buttons, text="Apply", command=apply_settings).pack(side="right")
        popup.protocol("WM_DELETE_WINDOW", close_popup)
        popup.bind("<Return>", lambda _event: apply_settings())
        popup.bind("<Escape>", lambda _event: close_popup())

    # ---------- copy / paste ----------
    def copy_frame(self):
        if not self.frames:
            return

        src = self.frame_paths[self.current_index]
        copied = Path("copied_frame.png")
        image = self.open_image_copy(src, "RGBA", "open frame to copy")
        if image is None:
            return
        if not self.save_image_retry(image, copied, "copy frame"):
            return

        if set_png_clipboard_from_path(copied):
            self.set_status("Copied alpha image to clipboard")
        elif set_file_clipboard([copied]):
            self.set_status("Copied alpha PNG file to clipboard")
        elif set_image_clipboard_from_path(copied):
            self.set_status("Copied image bitmap to clipboard; alpha may be flattened")
        else:
            self.set_status("Clipboard copy failed")

    def paste_frame(self):
        if not self.frames:
            return

        dst = self.frame_paths[self.current_index]
        current_alpha = None
        if dst.exists():
            current = self.open_image_copy(dst, "RGBA", "open current frame")
            if current is None:
                return
            current_alpha = current.getchannel("A")

        clipboard_image = get_image_from_clipboard()
        if clipboard_image is not None:
            pasted = clipboard_image.convert("RGBA")
            has_pasted_alpha = "A" in clipboard_image.getbands()
            if current_alpha is not None and not has_pasted_alpha:
                if pasted.size != current_alpha.size:
                    pasted = pasted.resize(current_alpha.size, Image.Resampling.LANCZOS)
                pasted.putalpha(current_alpha)
            if not self.save_image_retry(pasted, dst, "paste frame"):
                return
        else:
            src = None
            clipboard_paths = [Path(p) for p in get_file_clipboard_paths()]
            for path in clipboard_paths:
                if path.exists() and path.suffix.lower() in SUPPORTED_IMAGE_TYPES:
                    src = path
                    break

            if src is None:
                fallback = Path("copied_frame.png")
                if fallback.exists():
                    src = fallback

            if src is None:
                return

            def read_bands():
                with Image.open(src) as source_image:
                    return source_image.getbands()

            bands = self.retry_file_operation("inspect pasted image", read_bands, src)
            if bands is None:
                return
            has_pasted_alpha = "A" in bands
            pasted = self.open_image_copy(src, "RGBA", "open pasted image")
            if pasted is None:
                return
            if current_alpha is not None and not has_pasted_alpha:
                if pasted.size != current_alpha.size:
                    pasted = pasted.resize(current_alpha.size, Image.Resampling.LANCZOS)
                pasted.putalpha(current_alpha)
            if not self.save_image_retry(pasted, dst, "paste frame"):
                return

        self.invalidate_frame_cache(self.current_index)
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()

    def renumber_frame_files(self):
        self.release_file_caches()
        existing = sorted(TEMP_DIR.glob("frame_*.png"))
        temp_paths = []
        for i, path in enumerate(existing):
            temp_path = TEMP_DIR / f"_renumber_{i:06d}.png"
            if not self.rename_path_retry(path, temp_path):
                return False
            temp_paths.append(temp_path)

        for i, path in enumerate(temp_paths, start=1):
            if not self.rename_path_retry(path, TEMP_DIR / f"frame_{i:06d}.png"):
                return False

        self.frame_paths = sorted(TEMP_DIR.glob("frame_*.png"))
        self.frames = [p.name for p in self.frame_paths]
        return True

    def reset_after_frame_list_change(self):
        self.full_cache.clear()
        self.thumb_cache.clear()
        self.large_thumb_cache.clear()
        with self.wand_zone_lock:
            self.wand_zone_cache.clear()
            self.wand_preload_targets = []
        self.base_thumb_sizes = []
        self.large_thumb_sizes = []
        self.prefix_positions = []
        self.timeline_total_width = 0
        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()
        self.center_selected()

    def export_current_frame(self):
        if not self.frames:
            return
        save_path = filedialog.asksaveasfilename(
            title="Export current frame",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
        )
        if not save_path:
            return
        image = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open current frame")
        if image is None:
            return
        if not self.save_image_retry(image, save_path, "export current frame"):
            return
        self.set_status("Exported current frame")

    def resize_image_for_append(self, image, target_size, mode):
        target_w, target_h = target_size
        if mode == "Stretch":
            return image.resize(target_size, Image.Resampling.LANCZOS)

        if mode == "Scale To Fit":
            result = Image.new("RGBA", target_size, (0, 0, 0, 0))
            copy = image.copy()
            copy.thumbnail(target_size, Image.Resampling.LANCZOS)
            x = (target_w - copy.width) // 2
            y = (target_h - copy.height) // 2
            result.alpha_composite(copy, (x, y))
            return result

        if mode == "Center Crop":
            scale = max(target_w / image.width, target_h / image.height)
            size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            copy = image.resize(size, Image.Resampling.LANCZOS)
            left = max(0, (copy.width - target_w) // 2)
            top = max(0, (copy.height - target_h) // 2)
            return copy.crop((left, top, left + target_w, top + target_h))

        return image

    def ask_append_resize_mode(self, source_size, target_size):
        popup = Toplevel(self.tk_root)
        popup.title("Append Frame Size")
        popup.resizable(False, False)
        choice = {"value": None}

        main = Frame(popup, padx=14, pady=12)
        main.pack()
        Label(main, text=f"Image is {source_size[0]}x{source_size[1]}; video is {target_size[0]}x{target_size[1]}.").pack(anchor="w")
        Label(main, text="Choose how to resize the appended frame.").pack(anchor="w", pady=(4, 12))

        def choose(value):
            choice["value"] = value
            popup.destroy()

        buttons = Frame(main)
        buttons.pack(anchor="e")
        for label in ("Scale To Fit", "Center Crop", "Stretch", "Cancel"):
            Button(buttons, text=label, command=lambda value=label: choose(value)).pack(side="left", padx=(0, 8))

        popup.protocol("WM_DELETE_WINDOW", lambda: choose("Cancel"))
        popup.grab_set()
        self.tk_root.wait_window(popup)
        return choice["value"]

    def append_frame_after_current(self):
        if not self.frames:
            return
        path = filedialog.askopenfilename(
            title="Append image frame",
            filetypes=[("Image Files", " ".join(f"*{ext}" for ext in sorted(SUPPORTED_IMAGE_TYPES)))],
        )
        if not path:
            return

        current = self.open_image_copy(self.frame_paths[self.current_index], "RGBA", "open current frame")
        if current is None:
            return
        target_size = current.size
        image = self.open_image_copy(path, "RGBA", "open appended image")
        if image is None:
            return

        if image.size != target_size:
            mode = self.ask_append_resize_mode(image.size, target_size)
            if mode in (None, "Cancel"):
                return
            image = self.resize_image_for_append(image, target_size, mode)

        insert_index = self.current_index + 1
        temp_insert = TEMP_DIR / "_insert_frame.png"
        if not self.save_image_retry(image, temp_insert, "save inserted frame"):
            return

        self.release_file_caches()
        for i in range(len(self.frame_paths), insert_index, -1):
            src = TEMP_DIR / f"frame_{i:06d}.png"
            dst = TEMP_DIR / f"frame_{i + 1:06d}.png"
            if src.exists():
                if not self.rename_path_retry(src, dst):
                    return

        if not self.rename_path_retry(temp_insert, TEMP_DIR / f"frame_{insert_index + 1:06d}.png"):
            return
        if not self.renumber_frame_files():
            return
        self.current_index = insert_index
        self.reset_after_frame_list_change()
        self.set_status("Appended frame")

    def append_video_frames(self):
        if not self.frames:
            self.open_video()
            return
        if not self.has_ffmpeg_tools():
            self.show_ffmpeg_missing_help()
            return

        path = filedialog.askopenfilename(
            title="Append video or animation",
            filetypes=[("Video Files", SUPPORTED_VIDEO_TYPES)],
        )
        if not path:
            return

        video_path = Path(path)
        if not video_path.exists():
            self.set_status("File not found")
            return
        if video_path.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
            self.set_status("Unsupported video or animation file")
            return

        self.close_menus()
        current_size = self.get_current_frame_size()
        append_fps = self.detect_fps(video_path)
        self.loading_message = f"Appending {video_path.name}..."
        self.force_redraw()

        try:
            self.extract_frames_to_dir(video_path, APPEND_TEMP_DIR, clear_output=True)
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            self.loading_message = ""
            self.show_file_error("append video", video_path, exc)
            return

        append_paths = sorted(APPEND_TEMP_DIR.glob("frame_*.png"))
        if not append_paths:
            self.loading_message = ""
            self.set_status("No frames found in appended video")
            return

        first = self.open_image_copy(append_paths[0], "RGBA", "open appended video frame")
        if first is None:
            self.loading_message = ""
            return
        resize_mode = None
        if first.size != current_size:
            resize_mode = self.ask_append_resize_mode(first.size, current_size)
            if resize_mode in (None, "Cancel"):
                self.loading_message = ""
                return

        start_index = len(self.frame_paths) + 1
        self.release_file_caches()
        for offset, src in enumerate(append_paths):
            self.loading_message = f"Appending frames... {offset + 1}/{len(append_paths)}"
            if offset % 5 == 0:
                self.force_redraw()
            image = self.open_image_copy(src, "RGBA", "open appended video frame")
            if image is None:
                self.loading_message = ""
                return
            if image.size != current_size:
                image = self.resize_image_for_append(image, current_size, resize_mode)
            dst = TEMP_DIR / f"frame_{start_index + offset:06d}.png"
            if not self.save_image_retry(image, dst, "save appended video frame"):
                self.loading_message = ""
                return

        self.frame_paths = sorted(TEMP_DIR.glob("frame_*.png"))
        self.frames = [p.name for p in self.frame_paths]
        self.current_index = start_index - 1
        self.reset_after_frame_list_change()
        self.loading_message = ""

        fps_note = ""
        if abs(append_fps - self.fps) > 0.01:
            fps_note = f"; appended source was {append_fps:.3f} FPS"
        self.set_status(f"Appended {len(append_paths)} video frames{fps_note}", 5000)

    def delete_current_frame(self):
        if not self.frames:
            return

        delete_index = self.current_index
        delete_path = self.frame_paths[delete_index]
        self.release_file_caches()
        if not self.unlink_path_retry(delete_path):
            return

        if not self.renumber_frame_files():
            return
        self.current_index = max(0, min(delete_index, len(self.frames) - 1))

        if self.frames:
            self.reset_after_frame_list_change()
            self.set_status("Deleted current frame")
        else:
            self.preview_zoom = 1.0
            self.preview_offset = [0.0, 0.0]
            self.scroll_x = 0.0
            self.scroll_velocity = 0.0
            self.retarget_width = None
            self.retarget_height = None
            self.retarget_fps = None
            self.set_status("Deleted last frame")

    # ---------- menu ----------
    def close_menus(self):
        self.file_menu_open = False
        self.active_menu = None

    def exit_app(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    def get_file_menu_items(self):
        return [
            ("Open Video...", "O", self.open_video, True),
            ("Append Video...", "", self.append_video_frames, bool(self.frames)),
            ("Reload Source", "Ctrl+R", self.reload_video, self.video_path is not None),
            ("Retarget Size/FPS...", "R", self.retarget_size_fps, bool(self.frames)),
            ("Preview Animation", "P", self.show_animation_preview, bool(self.frames)),
            ("Export Video...", "S", self.export_video, bool(self.frames)),
            ("Export High Quality GIF...", "", self.export_high_quality_gif, bool(self.frames)),
            ("Exit", "", self.exit_app, True),
        ]

    def get_frame_menu_items(self):
        can_split_blend = bool(self.frames) and self.current_index >= 3 and (len(self.frames) - self.current_index - 1) >= 3
        can_loop_blend = len(self.frames) >= 8
        return [
            ("Copy Current Frame", "C", self.copy_frame, bool(self.frames)),
            ("Paste Over Current Frame", "V", self.paste_frame, bool(self.frames)),
            ("Append Frame After Current...", "", self.append_frame_after_current, bool(self.frames)),
            ("RIFE Double FPS...", "", self.open_rife_interpolation, bool(self.frames)),
            ("RIFE Blend Selected Split", "", self.rife_blend_selected_split, can_split_blend),
            ("RIFE Blend Loop Seam", "", self.rife_blend_loop, can_loop_blend),
            ("Export Current Frame...", "", self.export_current_frame, bool(self.frames)),
            ("Delete Current Frame", "Del", self.delete_current_frame, bool(self.frames)),
            ("First Frame", "Home", lambda: self.set_current_index(0), bool(self.frames)),
            ("Last Frame", "End", lambda: self.set_current_index(len(self.frames) - 1), bool(self.frames)),
            ("Reset Preview", "0", self.reset_preview_view, bool(self.frames)),
        ]

    def get_color_menu_items(self):
        return [
            ("Color Tools...", "H", self.open_color_tools, bool(self.frames)),
            ("Blend Selected With Adjacent", "", self.blend_selected_with_adjacent_frames, bool(self.frames)),
            ("Match Whole Video To Selected", "", self.match_video_to_selected_reference, bool(self.frames)),
        ]

    def get_background_menu_items(self):
        mode_label = "Mask Edit Off" if self.mask_edit_mode else "Mask Edit On"
        wand_label = "Wand Select Off" if self.wand_mode else "Wand Select On"
        return [
            (mode_label, "M", self.toggle_mask_edit_mode, bool(self.frames)),
            (wand_label, "W", self.toggle_wand_mode, bool(self.frames)),
            ("Remove By Color...", "", self.open_color_range_tools, bool(self.frames)),
            ("Clear Wand Selection", "", self.clear_wand_selection, self.wand_selection is not None),
            ("Fill Current Mask", "", self.fill_current_mask, bool(self.frames)),
            ("Erase Current Mask", "", self.clear_current_mask, bool(self.frames)),
            ("Magic Outline...", "", self.open_magic_outline_tools, bool(self.frames)),
            ("RMBG Settings...", "", self.open_rembg_settings, True),
            ("Remove BG Current", "", self.remove_background_current_frame, bool(self.frames)),
            ("Remove BG Whole Video", "", self.remove_background_whole_video, bool(self.frames)),
        ]

    def get_menu_items(self, menu_name):
        if menu_name == "File":
            return self.get_file_menu_items()
        if menu_name == "Frame":
            return self.get_frame_menu_items()
        if menu_name == "Color":
            return self.get_color_menu_items()
        if menu_name == "Background":
            return self.get_background_menu_items()
        return []

    def get_dropdown_rect(self, menu_name):
        item_h = 34
        width = 280
        menu_rect = self.menu_rects.get(menu_name, pygame.Rect(8, 8, 68, 34))
        return pygame.Rect(menu_rect.x, TOP_BAR_H - 2, width, item_h * len(self.get_menu_items(menu_name)) + 8)

    def handle_menu_click(self, mouse):
        if self.background_toggle_rect.collidepoint(mouse):
            self.cycle_preview_background()
            return True

        for menu_name, menu_rect in self.menu_rects.items():
            if menu_rect.collidepoint(mouse):
                self.active_menu = None if self.active_menu == menu_name else menu_name
                self.file_menu_open = self.active_menu == "File"
                return True

        if self.active_menu is None:
            return False

        dropdown = self.get_dropdown_rect(self.active_menu)
        if not dropdown.collidepoint(mouse):
            self.close_menus()
            return False

        item_h = 34
        y = dropdown.y + 4
        for label, _shortcut, action, enabled in self.get_menu_items(self.active_menu):
            item_rect = pygame.Rect(dropdown.x + 4, y, dropdown.w - 8, item_h)
            if item_rect.collidepoint(mouse):
                self.close_menus()
                if enabled:
                    action()
                else:
                    self.set_status(f"{label} is not available")
                return True
            y += item_h

        return True

    def handle_dropfile(self, file_path):
        path = Path(file_path)
        if path.suffix.lower() in SUPPORTED_VIDEO_EXTS:
            self.open_video_path(path)
        elif path.suffix.lower() in SUPPORTED_IMAGE_TYPES:
            self.open_image_path(path)
        else:
            self.set_status("Drop a supported video, animation, or image file")

    # ---------- input ----------
    def handle_mouse_button_down(self, event):
        mouse = event.pos
        preview_rect = self.get_preview_rect()
        timeline_rect = self.get_timeline_rect()

        if event.button == 1:
            if self.handle_menu_click(mouse):
                return
            if self.active_tool == "color_range" and preview_rect.collidepoint(mouse) and self.color_range_image_sampler is not None:
                image_pos = self.preview_to_image_pos(mouse)
                if image_pos is not None:
                    self.color_range_image_sampler(image_pos, False)
            elif self.wand_mode and preview_rect.collidepoint(mouse):
                image_pos = self.preview_to_image_pos(mouse)
                if image_pos is not None:
                    with self.wand_zone_lock:
                        cache_ready = self.current_index in self.wand_zone_cache
                    if not cache_ready:
                        self.set_status("Preparing wand zones... please wait", 5000)
                        self.loading_message = "Preparing wand zones... please wait"
                        self.force_redraw()
                    mods = pygame.key.get_mods()
                    if mods & pygame.KMOD_SHIFT:
                        self.wand_combine_mode = "add"
                    elif mods & (pygame.KMOD_CTRL | pygame.KMOD_META):
                        self.wand_combine_mode = "subtract"
                    else:
                        self.wand_combine_mode = "replace"
                    self.wand_dragging = True
                    self.wand_start_pos = image_pos
                    self.wand_start_tolerance = self.wand_tolerance
                    self.wand_drag_base = self.wand_selection.copy() if self.wand_selection is not None else None
                    self.wand_last_drag_tolerance = None
                    self.click_down_pos = mouse
                    self.update_wand_selection(image_pos, self.wand_combine_mode, self.wand_tolerance)
            elif self.mask_edit_mode and preview_rect.collidepoint(mouse):
                self.mask_dragging = True
                self.mask_paint_mode = "restore"
                self.paint_mask_at(mouse)
            elif preview_rect.collidepoint(mouse):
                self.dragging_preview = True
                self.preview_drag_last = mouse
            elif timeline_rect.collidepoint(mouse):
                self.dragging_timeline = True
                self.last_mouse_x = mouse[0]
                self.last_drag_dx = 0.0
                self.scroll_velocity = 0.0
                self.click_candidate = True
                self.click_down_pos = mouse
        elif event.button == 3:
            if self.active_tool == "color_range" and preview_rect.collidepoint(mouse) and self.color_range_image_sampler is not None:
                image_pos = self.preview_to_image_pos(mouse)
                if image_pos is not None:
                    self.color_range_image_sampler(image_pos, True)
            elif self.mask_edit_mode and preview_rect.collidepoint(mouse):
                self.mask_dragging = True
                self.mask_paint_mode = "erase"
                self.paint_mask_at(mouse)
        elif event.button == 2:
            if preview_rect.collidepoint(mouse):
                self.dragging_preview = True
                self.preview_drag_last = mouse
        elif event.button == 4:
            self.close_menus()
            if self.mask_edit_mode and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                self.adjust_mask_brush_size(1)
            else:
                self.zoom_preview(mouse, 1)
        elif event.button == 5:
            self.close_menus()
            if self.mask_edit_mode and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                self.adjust_mask_brush_size(-1)
            else:
                self.zoom_preview(mouse, -1)

    def handle_mouse_button_up(self, event):
        if event.button not in (1, 2, 3):
            return

        if self.dragging_timeline and self.click_candidate:
            for i in range(len(self.frames)):
                if self.get_thumb_rect(i).collidepoint(event.pos):
                    self.set_current_index(i)
                    break
        elif self.dragging_timeline:
            self.scroll_velocity = -self.last_drag_dx * 1.4

        self.dragging_timeline = False
        self.dragging_preview = False
        self.mask_dragging = False
        self.wand_dragging = False
        self.wand_drag_base = None
        self.click_candidate = False

    def handle_mouse_motion(self, event):
        if self.wand_dragging and self.wand_mode and self.wand_start_pos is not None:
            dx = event.pos[0] - self.click_down_pos[0] if self.click_down_pos else 0
            self.wand_tolerance = max(0, min(255, self.wand_start_tolerance + int(dx / 2)))
            if self.wand_tolerance != self.wand_last_drag_tolerance:
                self.wand_last_drag_tolerance = self.wand_tolerance
                self.update_wand_selection(self.wand_start_pos, self.wand_combine_mode, self.wand_tolerance)
        elif self.mask_dragging and self.mask_edit_mode:
            self.paint_mask_at(event.pos)
        elif self.dragging_timeline:
            dx = event.pos[0] - self.last_mouse_x
            self.scroll_x -= dx * DRAG_MULTIPLIER
            self.last_drag_dx = dx
            self.last_mouse_x = event.pos[0]
            self.clamp_scroll()
            if abs(event.pos[0] - self.click_down_pos[0]) > 6 or abs(event.pos[1] - self.click_down_pos[1]) > 6:
                self.click_candidate = False
        elif self.dragging_preview:
            dx = event.pos[0] - self.preview_drag_last[0]
            dy = event.pos[1] - self.preview_drag_last[1]
            self.preview_offset[0] += dx
            self.preview_offset[1] += dy
            self.clamp_preview_offset()
            self.preview_drag_last = event.pos
            self.needs_preview_refresh = True

    def handle_keydown(self, event):
        now = pygame.time.get_ticks()
        ctrl_held = bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))
        if event.key == pygame.K_LEFT:
            self.left_held = True
            self.left_next_repeat = now + KEY_REPEAT_DELAY_MS
            if self.frames:
                self.set_current_index(self.current_index - 1)
        elif event.key == pygame.K_RIGHT:
            self.right_held = True
            self.right_next_repeat = now + KEY_REPEAT_DELAY_MS
            if self.frames:
                self.set_current_index(self.current_index + 1)
        elif event.key == pygame.K_HOME:
            if self.frames:
                self.set_current_index(0)
        elif event.key == pygame.K_END:
            if self.frames:
                self.set_current_index(len(self.frames) - 1)
        elif event.key == pygame.K_o:
            self.open_video()
        elif event.key == pygame.K_r:
            if ctrl_held:
                self.reload_video()
            else:
                self.retarget_size_fps()
        elif event.key == pygame.K_p:
            self.show_animation_preview()
        elif event.key == pygame.K_h:
            self.open_color_tools()
        elif event.key == pygame.K_m:
            self.toggle_mask_edit_mode()
        elif event.key == pygame.K_w:
            self.toggle_wand_mode()
        elif event.key == pygame.K_s:
            self.export_video()
        elif event.key == pygame.K_c:
            self.copy_frame()
        elif event.key == pygame.K_v:
            self.paste_frame()
        elif event.key == pygame.K_DELETE:
            if self.wand_selection is not None and (self.wand_mode or self.mask_edit_mode or self.active_tool == "color_range"):
                self.apply_wand_selection_to_alpha(0)
            else:
                self.delete_current_frame()
        elif event.key == pygame.K_RETURN:
            if self.wand_selection is not None and (self.wand_mode or self.mask_edit_mode or self.active_tool == "color_range"):
                self.apply_wand_selection_to_alpha(255)
        elif event.key == pygame.K_INSERT:
            if self.wand_selection is not None and (self.wand_mode or self.mask_edit_mode or self.active_tool == "color_range"):
                self.apply_wand_selection_to_alpha(255)
        elif event.key == pygame.K_0:
            self.reset_preview_view()
        elif event.key == pygame.K_ESCAPE:
            if self.wand_selection is not None:
                self.clear_wand_selection()
            else:
                self.close_menus()

    def handle_keyup(self, event):
        if event.key == pygame.K_LEFT:
            self.left_held = False
        elif event.key == pygame.K_RIGHT:
            self.right_held = False

    # ---------- drawing ----------
    def get_top_bar_hints(self):
        if self.wand_mode:
            return ["Wand: Click Select", "Shift Add", "Ctrl Subtract", "Insert Restore", "Delete Remove Mask"]
        if self.mask_edit_mode:
            return ["Mask Edit: Left Add", "Right Remove", "Shift Wheel Brush", "Insert Restore", "Delete Remove Mask"]
        if self.active_tool == "color_range":
            return ["Color Range: Left Low", "Right High", "Insert Restore", "Delete Remove Mask"]
        return ["Drop video here to open", "Mouse Wheel Zoom", "Drag Preview Pan", "Left/Right Frame"]

    def draw_top_bar(self):
        w, _ = self.get_window_size()
        pygame.draw.rect(self.screen, PANEL, (0, 0, w, TOP_BAR_H))
        self.menu_rects = {}
        self.background_toggle_rect = pygame.Rect(w - 132, 8, 120, 34)

        x = 8
        for menu_name in ("File", "Frame", "Color", "Background"):
            label_surf = self.small_font.render(menu_name, True, TEXT)
            rect = pygame.Rect(x, 8, label_surf.get_width() + 28, 34)
            self.menu_rects[menu_name] = rect
            button_color = (46, 46, 46) if self.active_menu == menu_name else (38, 38, 38)
            pygame.draw.rect(self.screen, button_color, rect, border_radius=4)
            pygame.draw.rect(self.screen, (78, 78, 78), rect, 1, border_radius=4)
            self.screen.blit(label_surf, label_surf.get_rect(center=rect.center))
            x = rect.right + 6

        labels = self.get_top_bar_hints()
        x += 16
        for label in labels:
            surf = self.small_font.render(label, True, TEXT)
            if x + surf.get_width() + 22 > self.background_toggle_rect.x - 12:
                break
            self.screen.blit(surf, (x, 16))
            x += surf.get_width() + 22

        pygame.draw.rect(self.screen, (38, 38, 38), self.background_toggle_rect, border_radius=4)
        pygame.draw.rect(self.screen, (78, 78, 78), self.background_toggle_rect, 1, border_radius=4)
        bg_label = self.small_font.render(self.preview_background, True, TEXT)
        self.screen.blit(bg_label, bg_label.get_rect(center=self.background_toggle_rect.center))
        return

        button_color = (46, 46, 46) if self.file_menu_open else (38, 38, 38)
        pygame.draw.rect(self.screen, button_color, self.file_menu_rect, border_radius=4)
        pygame.draw.rect(self.screen, (78, 78, 78), self.file_menu_rect, 1, border_radius=4)
        file_label = self.small_font.render("File", True, TEXT)
        self.screen.blit(file_label, file_label.get_rect(center=self.file_menu_rect.center))

        labels = ["Drop video here to open", "Mouse Wheel Zoom", "Drag Preview Pan", "Left/Right Frame"]
        x = self.file_menu_rect.right + 22
        for label in labels:
            surf = self.small_font.render(label, True, TEXT)
            self.screen.blit(surf, (x, 16))
            x += surf.get_width() + 22

        return

        labels = [
            "O Open",
            "C Copy Image",
            "V Paste Image",
            "S Export",
            "Mouse Wheel Zoom",
            "Drag Preview Pan",
            "← → Frame",
            "0 Reset Zoom",
        ]
        x = 14
        for label in labels:
            surf = self.small_font.render(label, True, TEXT)
            self.screen.blit(surf, (x, 16))
            x += surf.get_width() + 22

    def draw_active_menu(self):
        if self.active_menu is None:
            return

        dropdown = self.get_dropdown_rect(self.active_menu)
        pygame.draw.rect(self.screen, (34, 34, 34), dropdown, border_radius=4)
        pygame.draw.rect(self.screen, (84, 84, 84), dropdown, 1, border_radius=4)

        mouse = pygame.mouse.get_pos()
        item_h = 34
        y = dropdown.y + 4
        for label, shortcut, _action, enabled in self.get_menu_items(self.active_menu):
            item_rect = pygame.Rect(dropdown.x + 4, y, dropdown.w - 8, item_h)
            if enabled and item_rect.collidepoint(mouse):
                pygame.draw.rect(self.screen, (58, 58, 58), item_rect, border_radius=3)

            color = TEXT if enabled else (120, 120, 120)
            label_surf = self.small_font.render(label, True, color)
            shortcut_surf = self.small_font.render(shortcut, True, color)
            self.screen.blit(label_surf, (item_rect.x + 10, item_rect.y + 9))
            self.screen.blit(shortcut_surf, (item_rect.right - shortcut_surf.get_width() - 10, item_rect.y + 9))
            y += item_h

    def draw_file_menu(self):
        self.draw_active_menu()
        return

        dropdown = self.get_file_dropdown_rect()
        pygame.draw.rect(self.screen, (34, 34, 34), dropdown, border_radius=4)
        pygame.draw.rect(self.screen, (84, 84, 84), dropdown, 1, border_radius=4)

        mouse = pygame.mouse.get_pos()
        item_h = 34
        y = dropdown.y + 4
        for label, shortcut, _action, enabled in self.get_file_menu_items():
            item_rect = pygame.Rect(dropdown.x + 4, y, dropdown.w - 8, item_h)
            if enabled and item_rect.collidepoint(mouse):
                pygame.draw.rect(self.screen, (58, 58, 58), item_rect, border_radius=3)

            color = TEXT if enabled else (120, 120, 120)
            label_surf = self.small_font.render(label, True, color)
            shortcut_surf = self.small_font.render(shortcut, True, color)
            self.screen.blit(label_surf, (item_rect.x + 10, item_rect.y + 9))
            self.screen.blit(shortcut_surf, (item_rect.right - shortcut_surf.get_width() - 10, item_rect.y + 9))
            y += item_h

    def draw_preview(self):
        rect = self.get_preview_rect()
        pygame.draw.rect(self.screen, (0, 0, 0), rect)
        pygame.draw.rect(self.screen, (60, 60, 60), rect, 1)

        if not self.frames:
            loading_text = self.loading_message if self.loading_message else "Use File > Open Video or drop a video/image here"
            msg = self.font.render(loading_text, True, TEXT)
            self.screen.blit(msg, msg.get_rect(center=rect.center))
            return

        self.refresh_preview_surface()
        if self.preview_surface is not None:
            self.screen.blit(self.preview_surface, rect.topleft)

        width, height, output_fps = self.get_retarget_settings()
        frame_text = self.font.render(
            f"Frame {self.current_index} / {len(self.frames) - 1}   Source {self.fps:.3f} FPS   Output {width}x{height} @ {output_fps:.3f} FPS   Zoom {self.preview_zoom:.2f}x",
            True,
            TEXT,
        )
        badge = pygame.Surface((frame_text.get_width() + 16, frame_text.get_height() + 10), pygame.SRCALPHA)
        badge.fill((0, 0, 0, 150))
        self.screen.blit(badge, (rect.x + 12, rect.y + 12))
        self.screen.blit(frame_text, (rect.x + 20, rect.y + 17))

        if self.status_message and pygame.time.get_ticks() < self.status_until:
            status = self.font.render(self.status_message, True, TEXT)
            status_badge = pygame.Surface((status.get_width() + 16, status.get_height() + 10), pygame.SRCALPHA)
            status_badge.fill((0, 0, 0, 150))
            self.screen.blit(status_badge, (rect.x + 12, rect.bottom - status.get_height() - 22))
            self.screen.blit(status, (rect.x + 20, rect.bottom - status.get_height() - 17))

        if self.mask_edit_mode:
            mouse = pygame.mouse.get_pos()
            if rect.collidepoint(mouse) and self.preview_to_image_pos(mouse) is not None:
                full = self.load_full_surface(self.current_index)
                img_w, img_h = full.get_size()
                fit_scale = min(rect.w / img_w, rect.h / img_h)
                scale = max(0.05, fit_scale * self.preview_zoom)
                radius = max(1, int(self.mask_brush_size * scale))
                color = (80, 180, 255) if self.mask_paint_mode == "restore" else (255, 100, 100)
                pygame.draw.circle(self.screen, color, mouse, radius, 2)
                pygame.draw.circle(self.screen, (255, 255, 255), mouse, max(1, radius // 6), 1)

        if self.wand_selection is not None and (self.wand_mode or self.mask_edit_mode or self.active_tool == "color_range"):
            self.draw_wand_selection_overlay(rect)

    def draw_wand_selection_overlay(self, rect):
        if self.wand_selection is None or not self.frames:
            return

        try:
            import numpy as np
        except ImportError:
            return

        full = self.load_full_surface(self.current_index)
        img_w, img_h = full.get_size()
        if self.wand_selection.shape != (img_h, img_w):
            return

        fit_scale = min(rect.w / img_w, rect.h / img_h)
        scale = max(0.05, fit_scale * self.preview_zoom)
        draw_w = max(1, int(img_w * scale))
        draw_h = max(1, int(img_h * scale))
        x = rect.x + (rect.w - draw_w) // 2 + int(self.preview_offset[0])
        y = rect.y + (rect.h - draw_h) // 2 + int(self.preview_offset[1])

        selection = self.wand_selection
        edge = selection.copy()
        edge[1:, :] &= selection[:-1, :]
        edge[:-1, :] &= selection[1:, :]
        edge[:, 1:] &= selection[:, :-1]
        edge[:, :-1] &= selection[:, 1:]
        edge = selection & ~edge

        overlay = np.zeros((img_h, img_w, 4), dtype=np.uint8)
        overlay[selection] = (80, 170, 255, 70)
        overlay[edge] = (255, 240, 60, 230)
        surf = pygame.image.frombuffer(overlay.tobytes(), (img_w, img_h), "RGBA").convert_alpha()
        surf = pygame.transform.scale(surf, (draw_w, draw_h))
        self.screen.blit(surf, (x, y))

    def draw_timeline(self):
        rect = self.get_timeline_rect()
        pygame.draw.rect(self.screen, PANEL, rect)
        pygame.draw.line(self.screen, (50, 50, 50), (rect.x, rect.y), (rect.right, rect.y), 1)

        if not self.frames or len(self.prefix_positions) != len(self.frames) or len(self.base_thumb_sizes) != len(self.frames) or len(self.large_thumb_sizes) != len(self.frames):
            return

        clip = self.screen.get_clip()
        self.screen.set_clip(rect)

        for i in range(len(self.frames)):
            thumb_rect = self.get_thumb_rect(i)
            if thumb_rect.right < rect.x - 50 or thumb_rect.x > rect.right + 50:
                continue

            surf = self.build_thumb(i, selected=(i == self.current_index))
            self.screen.blit(surf, thumb_rect.topleft)
            border = ACCENT if i == self.current_index else (55, 55, 55)
            border_w = 3 if i == self.current_index else 1
            pygame.draw.rect(self.screen, border, thumb_rect.inflate(4, 4), border_w)

            if i == self.current_index:
                text = self.small_font.render(str(i), True, TEXT)
                text_rect = text.get_rect(center=(thumb_rect.centerx, rect.bottom - 18))
                self.screen.blit(text, text_rect)

        center_x = rect.centerx
        pygame.draw.line(self.screen, (255, 255, 255), (center_x, rect.y + 8), (center_x, rect.bottom - 8), 1)
        self.screen.set_clip(clip)

    # ---------- loop ----------
    def update(self):
        now = pygame.time.get_ticks()

        if self.left_held and now >= self.left_next_repeat and self.frames:
            self.set_current_index(self.current_index - 1)
            self.left_next_repeat = now + KEY_REPEAT_INTERVAL_MS

        if self.right_held and now >= self.right_next_repeat and self.frames:
            self.set_current_index(self.current_index + 1)
            self.right_next_repeat = now + KEY_REPEAT_INTERVAL_MS

        if not self.dragging_timeline and abs(self.scroll_velocity) > 0.01:
            self.scroll_x += self.scroll_velocity
            self.scroll_velocity *= SCROLL_FRICTION
            self.clamp_scroll()
        else:
            self.scroll_velocity = 0.0

    def run(self):
        while True:
            for event in pygame.event.get():
                try:
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        return
                    elif event.type == pygame.VIDEORESIZE:
                        self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                        self.clamp_preview_offset()
                        self.needs_preview_refresh = True
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        self.handle_mouse_button_down(event)
                    elif event.type == pygame.MOUSEBUTTONUP:
                        self.handle_mouse_button_up(event)
                    elif event.type == pygame.MOUSEMOTION:
                        self.handle_mouse_motion(event)
                    elif event.type == pygame.KEYDOWN:
                        self.handle_keydown(event)
                    elif event.type == pygame.KEYUP:
                        self.handle_keyup(event)
                    elif event.type == pygame.DROPFILE:
                        self.handle_dropfile(event.file)
                except (OSError, PermissionError) as exc:
                    self.handle_filesystem_exception(exc)

            try:
                self.tk_root.update_idletasks()
                self.tk_root.update()
            except Exception:
                pass

            try:
                self.update()
                self.screen.fill(BG)
                self.draw_top_bar()
                self.draw_preview()
                self.draw_timeline()
                if self.active_menu is not None:
                    self.draw_active_menu()
                pygame.display.flip()
            except (OSError, PermissionError) as exc:
                self.handle_filesystem_exception(exc)
            self.clock.tick(60)


def main():
    app = FrameEditorApp()
    app.run()


if __name__ == "__main__":
    main()
