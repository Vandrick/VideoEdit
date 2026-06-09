import json
import shutil
import subprocess
import sys
import ctypes
import io
import time
from pathlib import Path

import pygame
from PIL import Image, ImageGrab, ImageTk
from tkinter import Tk, Toplevel, Label, Entry, Button, Frame, StringVar, filedialog

TEMP_DIR = Path("temp_frames")
BG = (18, 18, 18)
PANEL = (28, 28, 28)
TEXT = (235, 235, 235)
ACCENT = (255, 255, 255)

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
SUPPORTED_VIDEO_TYPES = ".mp4 .mov .avi .mkv .webm .m4v .gif"
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".gif"}
SUPPORTED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}

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


def get_image_from_clipboard():
    try:
        data = ImageGrab.grabclipboard()
        if isinstance(data, Image.Image):
            return data
    except Exception:
        pass
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
        self.file_menu_rect = pygame.Rect(8, 8, 68, 34)

        self.tk_root = Tk()
        self.tk_root.withdraw()

    # ---------- ffmpeg ----------
    def detect_fps(self, file_path):
        try:
            cmd = [
                "ffprobe",
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

    def extract_frames(self, video_path):
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(video_path), str(TEMP_DIR / "frame_%06d.png")], check=True)

    def force_redraw(self):
        self.screen.fill(BG)
        self.draw_top_bar()
        self.draw_preview()
        self.draw_timeline()
        if self.file_menu_open:
            self.draw_file_menu()
        pygame.display.flip()

    def open_video_path(self, path):
        path = Path(path)
        if not path.exists():
            self.set_status("File not found")
            return
        if path.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
            self.set_status("Unsupported video or animation file")
            return

        self.file_menu_open = False
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

    def make_even(self, value):
        value = max(2, int(value))
        return value if value % 2 == 0 else value + 1

    def get_current_frame_size(self):
        if not self.frame_paths:
            return None
        index = max(0, min(self.current_index, len(self.frame_paths) - 1))
        with Image.open(self.frame_paths[index]) as image:
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
            if self.preview_popup is popup:
                self.preview_popup = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", close_preview)

        preview_frames = []
        try:
            for frame_number, path in enumerate(self.frame_paths, start=1):
                if self.preview_popup is not popup or not popup.winfo_exists():
                    return

                image_label.configure(text=f"Preparing preview {frame_number}/{len(self.frame_paths)}")
                popup.update_idletasks()
                popup.update()

                with Image.open(path) as image:
                    image = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
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
        save_path = filedialog.asksaveasfilename(
            title="Save video",
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4")],
        )
        if not save_path:
            return

        temp_video = TEMP_DIR / "_video_only_export.mp4"
        width, height, output_fps = self.get_retarget_settings()

        subprocess.run(
            [
                "ffmpeg",
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

        if self.video_path is not None:
            try:
                subprocess.run(
                    [
                        "ffmpeg",
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
                shutil.copy(temp_video, save_path)
                self.set_status("Exported video only; audio copy failed")
        else:
            shutil.copy(temp_video, save_path)
            self.set_status("Exported video only")

    # ---------- cache ----------
    def load_full_surface(self, index):
        surf = self.full_cache.get(index)
        if surf is not None:
            return surf
        surf = pygame.image.load(str(self.frame_paths[index])).convert()
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
        cache[index] = thumb
        return thumb

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
        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True
        self.clamp_preview_offset()
        self.prime_caches_near_current()
        self.center_selected()

    def refresh_preview_surface(self):
        if not self.frames:
            return

        rect = self.get_preview_rect()
        full = self.load_full_surface(self.current_index)
        key = (self.current_index, rect.size, round(self.preview_zoom, 4), int(self.preview_offset[0]), int(self.preview_offset[1]))
        if key == self.preview_surface_key and self.preview_surface is not None:
            return

        img_w, img_h = full.get_size()
        fit_scale = min(rect.w / img_w, rect.h / img_h)
        scale = max(0.05, fit_scale * self.preview_zoom)
        draw_w = max(1, int(img_w * scale))
        draw_h = max(1, int(img_h * scale))
        scaled = pygame.transform.smoothscale(full, (draw_w, draw_h))

        surface = pygame.Surface((rect.w, rect.h))
        surface.fill((0, 0, 0))
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

    # ---------- copy / paste ----------
    def copy_frame(self):
        if not self.frames:
            return

        src = self.frame_paths[self.current_index]
        shutil.copy(src, "copied_frame.png")

        if set_image_clipboard_from_path(src):
            self.set_status("Copied image bitmap to clipboard")
        elif set_file_clipboard([src]):
            self.set_status("Copied file path to clipboard")
        else:
            self.set_status("Clipboard copy failed")

    def paste_frame(self):
        if not self.frames:
            return

        dst = self.frame_paths[self.current_index]

        clipboard_image = get_image_from_clipboard()
        if clipboard_image is not None:
            clipboard_image.convert("RGB").save(dst)
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

            shutil.copy(src, dst)

        for cache in (self.full_cache, self.thumb_cache, self.large_thumb_cache):
            cache.pop(self.current_index, None)

        self.preview_surface = None
        self.preview_surface_key = None
        self.needs_preview_refresh = True
        self.prime_caches_near_current()
        self.rebuild_timeline_metrics()

    def delete_current_frame(self):
        if not self.frames:
            return

        delete_index = self.current_index
        delete_path = self.frame_paths[delete_index]
        try:
            delete_path.unlink()
        except OSError:
            self.set_status("Could not delete current frame")
            return

        remaining_paths = [path for i, path in enumerate(self.frame_paths) if i != delete_index]
        temp_paths = []
        for i, path in enumerate(remaining_paths):
            temp_path = TEMP_DIR / f"_renumber_{i:06d}.png"
            path.rename(temp_path)
            temp_paths.append(temp_path)

        for i, path in enumerate(temp_paths, start=1):
            path.rename(TEMP_DIR / f"frame_{i:06d}.png")

        self.frame_paths = sorted(TEMP_DIR.glob("frame_*.png"))
        self.frames = [p.name for p in self.frame_paths]
        self.current_index = max(0, min(delete_index, len(self.frames) - 1))

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

        if self.frames:
            self.prime_caches_near_current()
            self.rebuild_timeline_metrics()
            self.center_selected()
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
    def get_file_menu_items(self):
        return [
            ("Open Video...", "O", self.open_video, True),
            ("Retarget Size/FPS...", "R", self.retarget_size_fps, bool(self.frames)),
            ("Preview Animation", "P", self.show_animation_preview, bool(self.frames)),
            ("Export Video...", "S", self.export_video, bool(self.frames)),
            ("Copy Current Frame", "C", self.copy_frame, bool(self.frames)),
            ("Paste Over Current Frame", "V", self.paste_frame, bool(self.frames)),
            ("Delete Current Frame", "Del", self.delete_current_frame, bool(self.frames)),
            ("Reset Preview", "0", self.reset_preview_view, bool(self.frames)),
        ]

    def get_file_dropdown_rect(self):
        item_h = 34
        width = 260
        return pygame.Rect(self.file_menu_rect.x, TOP_BAR_H - 2, width, item_h * len(self.get_file_menu_items()) + 8)

    def handle_menu_click(self, mouse):
        if self.file_menu_rect.collidepoint(mouse):
            self.file_menu_open = not self.file_menu_open
            return True

        if not self.file_menu_open:
            return False

        dropdown = self.get_file_dropdown_rect()
        if not dropdown.collidepoint(mouse):
            self.file_menu_open = False
            return False

        item_h = 34
        y = dropdown.y + 4
        for label, _shortcut, action, enabled in self.get_file_menu_items():
            item_rect = pygame.Rect(dropdown.x + 4, y, dropdown.w - 8, item_h)
            if item_rect.collidepoint(mouse):
                self.file_menu_open = False
                if enabled:
                    action()
                else:
                    self.set_status(f"{label} needs an open video")
                return True
            y += item_h

        return True

    def handle_dropfile(self, file_path):
        path = Path(file_path)
        if path.suffix.lower() in SUPPORTED_VIDEO_EXTS:
            self.open_video_path(path)
        else:
            self.set_status("Drop a supported video or animation file")

    # ---------- input ----------
    def handle_mouse_button_down(self, event):
        mouse = event.pos
        preview_rect = self.get_preview_rect()
        timeline_rect = self.get_timeline_rect()

        if event.button == 1:
            if self.handle_menu_click(mouse):
                return
            if preview_rect.collidepoint(mouse):
                self.dragging_preview = True
                self.preview_drag_last = mouse
            elif timeline_rect.collidepoint(mouse):
                self.dragging_timeline = True
                self.last_mouse_x = mouse[0]
                self.last_drag_dx = 0.0
                self.scroll_velocity = 0.0
                self.click_candidate = True
                self.click_down_pos = mouse
        elif event.button == 4:
            self.file_menu_open = False
            self.zoom_preview(mouse, 1)
        elif event.button == 5:
            self.file_menu_open = False
            self.zoom_preview(mouse, -1)

    def handle_mouse_button_up(self, event):
        if event.button != 1:
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
        self.click_candidate = False

    def handle_mouse_motion(self, event):
        if self.dragging_timeline:
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
            self.retarget_size_fps()
        elif event.key == pygame.K_p:
            self.show_animation_preview()
        elif event.key == pygame.K_s:
            self.export_video()
        elif event.key == pygame.K_c:
            self.copy_frame()
        elif event.key == pygame.K_v:
            self.paste_frame()
        elif event.key == pygame.K_DELETE:
            self.delete_current_frame()
        elif event.key == pygame.K_0:
            self.reset_preview_view()
        elif event.key == pygame.K_ESCAPE:
            self.file_menu_open = False

    def handle_keyup(self, event):
        if event.key == pygame.K_LEFT:
            self.left_held = False
        elif event.key == pygame.K_RIGHT:
            self.right_held = False

    # ---------- drawing ----------
    def draw_top_bar(self):
        w, _ = self.get_window_size()
        pygame.draw.rect(self.screen, PANEL, (0, 0, w, TOP_BAR_H))
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

    def draw_file_menu(self):
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
            loading_text = self.loading_message if self.loading_message else "Use File > Open Video or drop a video here"
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

            try:
                self.tk_root.update_idletasks()
                self.tk_root.update()
            except Exception:
                pass

            self.update()
            self.screen.fill(BG)
            self.draw_top_bar()
            self.draw_preview()
            self.draw_timeline()
            if self.file_menu_open:
                self.draw_file_menu()
            pygame.display.flip()
            self.clock.tick(60)


def main():
    app = FrameEditorApp()
    app.run()


if __name__ == "__main__":
    main()
