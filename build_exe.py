"""
Build script to compile ANG Automotive into a standalone Windows .exe executable.
"""

import os
import sys
import shutil
import subprocess

def build_windows_exe():
    print("=================================================================")
    print("  ANG AUTOMOTIVE - WINDOWS .EXE COMPILATION SUITE")
    print("=================================================================")

    # Clean previous build artifacts
    for d in ["build", "dist"]:
        if os.path.exists(d):
            print(f"Cleaning {d}/ directory...")
            shutil.rmtree(d)

    # Run PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "ANG_BMW_Tuner.spec"
    ]

    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        exe_path = os.path.join("dist", "ANG_BMW_Tuner.exe")
        print("\n=================================================================")
        print(f" BUILD SUCCESSFUL!")
        print(f" Executable generated at: {os.path.abspath(exe_path)}")
        print("=================================================================\n")
    else:
        print(f"\n[ERROR] Build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build_windows_exe()
