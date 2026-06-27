#!/usr/bin/env python3
"""Build a ddrescue mapfile covering only the clusters used by a set of files.

Reads an ntfsfindbad-style log (one 'inode=NNNN' per line), looks up each
inode's data runs with The Sleuth Kit's `istat`, coalesces the clusters into
runs, and emits a synthetic ddrescue mapfile marking just those bytes as
recovered ('+'). `ddrescuelog --complete-mapfile` then fills the gaps as
non-tried, so the result can be fed back to ddrescue to target only the
bytes belonging to the listed files.
"""

import argparse
import subprocess
import re
import sys
import tempfile
import os


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("findbad_log",
                   help="ddru_ntfsfindbad output log (default ntfsfindbad.log), or a "
                        "filtered extract of it, to read 'inode=NNNN' lines from")
    p.add_argument("image",
                   help="ddrescue output image: a block file representing the disk the "
                        "NTFS partition lives in (not the mapfile)")
    p.add_argument("-o", "--offset", type=int, required=True,
                   help="partition start, in bytes (e.g. sdb2 start)")
    p.add_argument("-s", "--sector-size", type=int, default=512,
                   help="sector size in bytes; the partition start in sectors "
                        "(passed to istat -o) is offset/sector-size (default: 512)")
    p.add_argument("-c", "--cluster-size", type=int, default=4096,
                   help="NTFS cluster size in bytes (default: 4096)")
    p.add_argument("-m", "--max-cluster", type=int, default=None,
                   help="reject cluster numbers >= this value (sentinels/junk); "
                        "default: no upper bound")
    p.add_argument("-f", "--file", default="domain_files.log",
                   help="completed ddrescue mapfile to write (default: domain_files.log)")
    return p.parse_args(argv)


def read_inodes(path):
    """Pull unique inode numbers from an ntfsfindbad log.

    Matches 'inode=NNNN' anchored at line start so a wrapped path can't interfere.
    """
    inode_re = re.compile(r'^inode=(\d+)')
    inodes = []
    seen = set()
    with open(path) as f:
        for line in f:
            m = inode_re.match(line)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                inodes.append(m.group(1))
    return inodes


def collect_clusters(inodes, image, sector_offset, max_cluster):
    """Run `istat` on each inode and collect its data-unit (cluster) numbers."""
    # A line is a data-unit list only if it's entirely whitespace-separated integers.
    num_line = re.compile(r'^\s*\d+(?:\s+\d+)*\s*$')
    clusters = set()
    for inode in inodes:
        try:
            out = subprocess.run(
                ["istat", "-o", str(sector_offset), image, inode],
                capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError as e:
            print(f"istat failed for inode {inode}: {e.stderr.strip()}", file=sys.stderr)
            continue
        for ln in out.splitlines():
            if num_line.match(ln):
                for tok in ln.split():
                    c = int(tok)
                    if max_cluster is None or c < max_cluster:
                        clusters.add(c)
    return clusters


def coalesce_runs(clusters):
    """Coalesce consecutive cluster numbers into (start_cluster, length) runs."""
    runs = []
    start = prev = None
    for c in sorted(clusters):
        if start is None:
            start = prev = c
        elif c == prev + 1:
            prev = c
        else:
            runs.append((start, prev - start + 1))
            start = prev = c
    if start is not None:
        runs.append((start, prev - start + 1))
    return runs


def write_synthetic(path, runs, offset, cluster_size):
    """Write a synthetic ddrescue mapfile: a leading '?' status line then the runs.

    The leading non-tried ('?') entry plus --complete-mapfile fills every gap,
    leaving only the listed files' bytes marked '+'.
    """
    with open(path, "w") as out:
        out.write("0x00000000     ?\n")
        for s, length in runs:
            out.write(f"0x{offset + s*cluster_size:x}  0x{length*cluster_size:x}  +\n")


def main(argv=None):
    args = parse_args(argv)

    inodes = read_inodes(args.findbad_log)
    print(f"{len(inodes)} inodes read from {args.findbad_log}", file=sys.stderr)

    sector_offset = args.offset // args.sector_size
    clusters = collect_clusters(inodes, args.image, sector_offset, args.max_cluster)
    runs = coalesce_runs(clusters)

    total = sum(length * args.cluster_size for _, length in runs)
    print(f"{len(inodes)} files, {len(clusters)} clusters, "
          f"{total/1048576:.1f} MB across {len(runs)} runs")

    # Build the synthetic mapfile in a temp file, removed once we're done.
    fd, synthetic = tempfile.mkstemp(suffix=".map", prefix="synthetic-")
    os.close(fd)
    try:
        write_synthetic(synthetic, runs, args.offset, args.cluster_size)
        try:
            with open(args.file, "w") as out:
                subprocess.run(["ddrescuelog", "--complete-mapfile", synthetic],
                               stdout=out, check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(f"ddrescuelog --complete-mapfile failed: {e}")
    finally:
        os.unlink(synthetic)

    print(f"\n--- ddrescuelog -t {args.file} ---")
    subprocess.run(["ddrescuelog", "-t", args.file])


if __name__ == "__main__":
    main()
