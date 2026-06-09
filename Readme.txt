Video Frame Editor

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

Optional background removal
Background removal uses rembg if it is installed. The editor still works without it, but the Background > Remove BG options will show an install message.

CPU install:

python -m pip install rembg onnxruntime

Or with the Windows Python launcher:

py -m pip install rembg onnxruntime

Test rembg:

python -c "from rembg import remove; print('rembg ready')"

or:

py -c "from rembg import remove; print('rembg ready')"

Optional GPU install
Only try this after CPU mode works:

python -m pip install rembg onnxruntime-gpu

GPU mode may require matching NVIDIA drivers and CUDA support.

Notes
- The first background-removal run may download model files. That is normal.
- If rembg fails to install on Python 3.14, use Python 3.11 or 3.12 in a virtual environment.
- High quality GIF export requires FFmpeg.
