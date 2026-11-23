"""Source-only handoff ZIP: no local logs, secrets, backups or model weights."""
from __future__ import annotations

import subprocess
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "docs/static/downloads/medtrace-nexent-vision-v281.zip"


def main():
    output = subprocess.check_output([
        "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--",
        "phase1", "phase2", "docs", "Dockerfile", ".env.example", "README.md",
    ], cwd=str(ROOT))
    paths = sorted(set(output.decode("utf-8").split("\0")) - {""})
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(str(TARGET), "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative in paths:
            source = ROOT / relative
            if source == TARGET or source.suffix == ".zip" or not source.is_file():
                continue
            if source.name.startswith(".env") and source.name != ".env.example":
                continue
            if any(part in {"logs", "backups", "__pycache__"} for part in source.parts):
                continue
            bundle.write(str(source), "MedTrace/" + relative)
            count += 1
        bundle.write(str(ROOT / "phase2/nexent_vision/开始这里.md"), "MedTrace/开始这里_图片理解接入.md")
    with zipfile.ZipFile(str(TARGET)) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
    print("Built {} source files, {} bytes: {}".format(count, TARGET.stat().st_size, TARGET))


if __name__ == "__main__":
    main()
