"""One-glance liveness status for the Foundry Pass 1 measured run.

Reads only the filesystem ground truth, so it cannot lie about progress:
if the newest artifact is stale and a sweep process is absent, we are
stalled; if file activity is recent, we are working.
"""

import glob
import os
import subprocess
import time

OUT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "out")


def age(path):
    return time.time() - os.path.getmtime(path)


def newest(pattern):
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def main():
    candidates = sorted(glob.glob(os.path.join(OUT, "candidates", "*.json")))
    verified = glob.glob(os.path.join(OUT, "verified", "*.json"))
    packets = glob.glob(os.path.join(OUT, "packets", "*.md"))
    dispositions = glob.glob(os.path.join(OUT, "dispositions", "*"))
    print(f"extracted : {len(candidates)}/38 sections")
    print(f"verified  : {len(verified)}/38 sections")
    print(f"packets   : {len(packets)} emitted, "
          f"{len(packets) - len(dispositions)} awaiting disposition "
          f"(WIP cap 5)")
    latest = newest(os.path.join(OUT, "**", "*"))
    if latest:
        minutes = age(latest) / 60
        print(f"last write: {os.path.relpath(latest, OUT)} "
              f"({minutes:.1f} min ago)")
    sweep = subprocess.run(
        ["pgrep", "-f", "run_extraction.py extract"],
        capture_output=True, text=True)
    sweep_alive = bool(sweep.stdout.strip())
    print(f"sweep proc: {'RUNNING' if sweep_alive else 'not running'}")
    fresh = latest and age(latest) < 180
    stale = latest and age(latest) > 720
    if fresh:
        print("verdict   : ALIVE — work is advancing")
    elif sweep_alive and stale:
        print("verdict   : SUSPECT — sweep process exists but nothing "
              "written for >12 min (likely a hung call); tell CC")
    elif sweep_alive:
        print("verdict   : ALIVE — sweep running, between writes")
    elif len(candidates) >= 38:
        print("verdict   : extraction complete — next stage pending")
    else:
        print("verdict   : STALLED — no sweep process and no recent "
              "writes; tell CC")


if __name__ == "__main__":
    main()
