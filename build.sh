#!/bin/bash
# Linux build: python cc.py [source.ts] [output.o] && gcc link && run
# Requires: python3, llvmlite (pip install llvmlite or apt install python3-llvmlite), gcc
set -e
SRC="${1:-test.ts}"
OUT_O="${2:-output.o}"
EXE="${3:-a.out}"
python3 cc.py "$SRC" "$OUT_O"
gcc "$OUT_O" -o "$EXE"
./"$EXE"
