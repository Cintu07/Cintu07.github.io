"""Shrinks a track so it is fit for a web page, and drops it in assets/music/ where the player finds it.

    pip install imageio-ffmpeg        (a bundled ffmpeg, nothing else to install)
    python tools/compress_music.py ~/Downloads/big-mix.mp3
    python tools/compress_music.py big-mix.mp3 --kbps 64 --mono        smaller, still fine for background music
    python tools/compress_music.py big-mix.mp3 --start 90 --minutes 4  keep a four minute stretch, faded at both ends

A page only ever needs a few MB of music. github refuses a file over 100 MB, a visitor should not wait on 150,
and the player streams the track, so what matters is the bitrate and how long the loop is.
Embedded cover art and tags are dropped, which on its own can be several MB.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB_FILE_LIMIT_MB = 95  # github rejects a push with a file over 100


def find_ffmpeg():
    exe = os.environ.get("IMAGEIO_FFMPEG_EXE") or shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("no ffmpeg found. run:  pip install imageio-ffmpeg")


def probe(ffmpeg, path):
    """duration in seconds and bitrate in kb/s, read from what ffmpeg prints about the file"""
    out = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+).*?bitrate: (\d+) kb/s", out, re.S)
    if not m:
        sys.exit(f"could not read {path} as audio")
    h, mi, s, kbps = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s), int(kbps)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "track"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="default: assets/music/<name>.mp3")
    ap.add_argument("--kbps", type=int, default=96, help="bitrate, 96 is a good default, 64 for the smallest that still sounds fine")
    ap.add_argument("--mono", action="store_true", help="one channel, half the size at the same bitrate quality")
    ap.add_argument("--start", type=float, default=0, help="seconds to skip from the start")
    ap.add_argument("--minutes", type=float, help="keep only this many minutes")
    ap.add_argument("--fade", type=float, default=2, help="seconds of fade at each end of a trimmed track, 0 for none")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg()
    src = args.input.expanduser().resolve()
    if not src.is_file():
        sys.exit(f"{src} is not a file")
    total, src_kbps = probe(ffmpeg, src)
    length = min(args.minutes * 60 if args.minutes else total, total - args.start)
    if length <= 0:
        sys.exit("nothing left after --start")

    out = (args.output or ROOT / "assets" / "music" / f"{slug(src.stem)}.mp3").resolve()
    if out == src:
        sys.exit("the output would overwrite the input")
    out.parent.mkdir(parents=True, exist_ok=True)

    trimmed = bool(args.minutes) or args.start > 0
    filters = []
    if trimmed and args.fade > 0 and length > args.fade * 4:
        filters = [f"afade=t=in:d={args.fade}", f"afade=t=out:st={length - args.fade}:d={args.fade}"]

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if args.start:
        cmd += ["-ss", str(args.start)]
    cmd += ["-i", str(src), "-t", str(length), "-vn", "-map_metadata", "-1", "-ac", "1" if args.mono else "2", "-ar", "44100"]
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += ["-c:a", "libmp3lame", "-b:a", f"{args.kbps}k", str(out)]
    subprocess.run(cmd, check=True)

    before, after = src.stat().st_size / 1e6, out.stat().st_size / 1e6
    print(f"{src.name}: {before:.1f} MB, {total / 60:.1f} min at {src_kbps} kb/s")
    print(f"{out.relative_to(ROOT) if ROOT in out.parents else out}: {after:.1f} MB, {length / 60:.1f} min at {args.kbps} kb/s{' mono' if args.mono else ''}  ({before / after:.1f}x smaller)")
    if after > GITHUB_FILE_LIMIT_MB:
        print("still over github's 100 MB file limit. use --minutes to keep a shorter stretch, or --kbps 64 --mono")
    elif after > 8:
        print("that is a lot of music for a web page. --minutes 5 keeps a loop-length stretch, --kbps 64 --mono shrinks it further")


if __name__ == "__main__":
    main()
