#!/usr/bin/env python3
"""Build the GTK 3 input method module on the Linux system that runs Code."""
import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


SOURCE = Path(__file__).resolve().parents[1] / "assets/desktop/standalone-code/ime/gtk.c"
DEPENDENCIES = "sudo apt install gcc pkg-config libgtk-3-dev"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Run this in the Linux guest where VS Code runs")
    if not all(shutil.which(tool) for tool in ("gcc", "pkg-config")):
        parser.error(f"Install GTK build tools with {DEPENDENCIES}")
    gtk = subprocess.run(["pkg-config", "--cflags", "--libs", "gtk+-3.0", "gmodule-2.0"],
                         text=True, capture_output=True, check=False)
    if gtk.returncode:
        parser.error(f"Install GTK development files with {DEPENDENCIES}")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vscode-ime-", dir=output.parent) as work:
        library = Path(work) / "im-tablet-vscode.so"
        subprocess.run(["gcc", "-std=c11", "-fPIC", "-shared", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-Wl,-z,defs", "-o", str(library), str(SOURCE), *shlex.split(gtk.stdout)], check=True)
        library.replace(output)
    print(output)


if __name__ == "__main__":
    main()
