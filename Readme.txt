Video Frame Editor

Used to convert / create Videos using FFmpeg.
AI Color correction and AI background removal.
Plus some manual tools to clean up any mistakes made in the process.
Designed for very short videos.
I mostly use it to clean up and remove backgrounds for AI generated sprites from Wan 2.2.

Required
- Python 3.11, 3.12, or 3.14
- FFmpeg 6.x or newer available on PATH
- Python packages from requirements.txt

Install required packages
From this project folder:

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

If the python command is not available on Windows, try:

py -m pip install --upgrade pip
py -m pip install -r requirements.txt

FFmpeg:
https://ffmpeg.org/

Install FFmpeg beside the app
Open PowerShell in the folder that contains VideoEdit.exe, or in this project folder when running from source, then paste:

$ErrorActionPreference = "Stop"
$zip = Join-Path (Get-Location) "ffmpeg-release-essentials.zip"
$tmp = Join-Path (Get-Location) "ffmpeg_extract"
Invoke-WebRequest "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $zip -DestinationPath $tmp -Force
$bin = Get-ChildItem $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1 -ExpandProperty DirectoryName
Copy-Item (Join-Path $bin "ffmpeg.exe") (Join-Path (Get-Location) "ffmpeg.exe") -Force
Copy-Item (Join-Path $bin "ffprobe.exe") (Join-Path (Get-Location) "ffprobe.exe") -Force
Remove-Item $tmp -Recurse -Force
Remove-Item $zip -Force
.\ffmpeg.exe -version

This keeps FFmpeg local to the app folder instead of changing the system PATH.

Optional RIFE frame interpolation
Frame > RIFE Double FPS uses rife-ncnn-vulkan if it is installed beside the app, in tools\rife-ncnn-vulkan, or on PATH.
Frame > RIFE Blend Selected Split is enabled when the selected frame has at least 3 frames before it and 3 frames after it.
Frame > RIFE Blend Loop Seam is enabled when the animation has at least 8 frames. It uses loop-relative frames -3, -2, -1, 2, 3, 4, then replaces the first 3 frames and rebuilds the end seam with the generated transition.

The blend tools stage 3 frames from each side, run RIFE 2x, keep the center generated frames, then lerp color matching from the left reference frame to the right reference frame.

Download:
https://github.com/nihui/rife-ncnn-vulkan/releases

Extract the portable Windows build exactly as it comes in the ZIP, then either copy that extracted folder beside VideoEdit.exe or place it here:

tools\rife-ncnn-vulkan

The model folders should sit directly beside rife-ncnn-vulkan.exe, for example:

tools\rife-ncnn-vulkan\rife-anime
tools\rife-ncnn-vulkan\rife-v4.6

The ncnn Vulkan build is portable and does not need CUDA or PyTorch.

Appending video
File > Append Video decodes another video or animation and adds its frames after the current loaded frames.
If the appended video has a different frame size, choose Scale To Fit, Center Crop, or Stretch.
The current project FPS is kept; the status bar notes when the appended video's source FPS differs.

Optional background removal
Background removal uses rembg if it is installed. The editor still works without it, but the Background > Remove BG options will show an install message.

CPU install:

python -m pip install "rembg[cpu]"

Or with the Windows Python launcher:

py -m pip install "rembg[cpu]"

Test rembg:

python -c "from rembg import remove; print('rembg ready')"

or:

py -c "from rembg import remove; print('rembg ready')"

Optional GPU install
Only try this after CPU mode works:

python -m pip install "rembg[gpu]"

GPU mode may require matching NVIDIA drivers and CUDA support.

Notes
- The first background-removal run may download model files. That is normal.
- If rembg fails to install on Python 3.14, use Python 3.11 or 3.12 in a virtual environment.
- High quality GIF export requires FFmpeg.
