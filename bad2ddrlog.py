#!/usr/bin/env python3
import subprocess, re, sys

BAD  = "extract.log"               # filtered ntfsfindbad log
IMG  = "/mnt/backup/lynnedisk.img" # disk img created by ddrescue
OFF  = 105906176      # partition start in bytes, e.g. sdb2
CS   = 4096           # cluster size (8 sectors x 512)
SECT_OFFSET = "206848"
MAX_CLUSTER = 1952393216 // 8   # 244049152; reject sentinels/junk at or above

# --- Stage 0: pull inode numbers from the findbad log ---
# Matches 'inode=NNNN' anchored at line start so a wrapped path can't interfere.
inode_re = re.compile(r'^inode=(\d+)')
inodes = []
seen = set()
with open(BAD) as f:
    for line in f:
        m = inode_re.match(line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            inodes.append(m.group(1))
print(f"{len(inodes)} inodes read from {BAD}", file=sys.stderr)

# A line is a data-unit list only if it's entirely whitespace-separated integers
num_line = re.compile(r'^\s*\d+(?:\s+\d+)*\s*$')

# --- Stage 1: collect cluster numbers from each file's MFT record ---
clusters = set()
with open("inodes.txt") as f:
    for line in f:
        inode = line.strip()
        if not inode:
            continue
        try:
            out = subprocess.run(
                ["istat", "-o", SECT_OFFSET, IMG, inode],
                capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError as e:
            print(f"istat failed for inode {inode}: {e.stderr.strip()}", file=sys.stderr)
            continue
        for ln in out.splitlines():
            if num_line.match(ln):
                for tok in ln.split():
                    c = int(tok)
                    if c < MAX_CLUSTER:        # drop 4294967295 sentinels etc.
                        clusters.add(c)

# --- Stage 2: coalesce consecutive clusters into runs, convert to byte ranges ---
runs_list = []   # each entry: (start_cluster, length_in_clusters)
start = prev = None
for c in sorted(clusters):
    if start is None:
        start = prev = c
    elif c == prev + 1:
        prev = c
    else:
        runs_list.append((start, prev - start + 1))
        start = prev = c
if start is not None:
    runs_list.append((start, prev - start + 1))


total = sum(length * CS for _, length in runs_list)
with open("blocks.txt", "w") as out:
    for s, length in runs_list:
        out.write(f"0x{OFF + s*CS:x}  0x{length*CS:x}  +\n")
print(f"{len(inodes)} files, {len(clusters)} clusters, "
      f"{total/1048576:.1f} MB across {len(runs_list)} runs")

# --- Stage 3: build synthetic mapfile from the same run list ---
# A ddrescue mapfile needs a status line before the block list. The leading
# non-tried ('?') entry plus --complete-mapfile fills every gap, leaving only
# your files marked '+'.
with open("synthetic.map", "w") as out:
    out.write("0x00000000     ?\n")
    for s, length in runs_list:
        out.write(f"0x{OFF + s*CS:x}  0x{length*CS:x}  +\n")

# --- Stage 4: complete the mapfile and show its status ---
try:
    with open("domain_files.log", "w") as out:
        subprocess.run(["ddrescuelog", "--complete-mapfile", "synthetic.map"],
                       stdout=out, check=True)
except subprocess.CalledProcessError as e:
    sys.exit(f"ddrescuelog --complete-mapfile failed: {e}")

print("\n--- ddrescuelog -t domain_files.log ---")
subprocess.run(["ddrescuelog", "-t", "domain_files.log"])
