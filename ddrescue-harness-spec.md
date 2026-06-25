# ddrescue Recovery Harness — Specification

**Status:** Draft for implementation
**Audience:** Developer building an automated wrapper around GNU ddrescue
**Target tool:** GNU ddrescue (gddrescue) ≥ 1.22, on Linux

---

## 1. Purpose and scope

This document specifies a harness that drives GNU ddrescue through an unattended recovery of a **failing block device** — specifically a device that intermittently **hangs or drops off the bus** and must be **power-cycled** to recover. The harness exists to remove the human from the babysitting loop: detect stalls, power-cycle the source device, re-verify device identity, and relaunch ddrescue with the correct flags and direction until the easily-readable data has been fully harvested.

The harness orchestrates ddrescue; it does **not** reimplement ddrescue's recovery algorithm. All actual reads, the mapfile, and the recovery phases remain ddrescue's responsibility.

### In scope
- Phased recovery strategy (fast copy first, scrape later).
- Stall/hang detection that does **not** rely on ddrescue's own timeout.
- Automated power-cycling of the source device and safe relaunch.
- Direction alternation (forward / reverse) to attack unread regions from both ends.
- Correct handling of interrupted-block demotion (the `--try-again` problem, §7).
- Detecting when the copy phase is genuinely complete (§8).
- Hard safety guarantees around device identity and mapfile integrity (§10).

### Out of scope (see §15)
- Filesystem-level repair or extraction from the recovered image.
- Imaging healthy drives (use plain `ddrescue` or `dd`).
- Hardware imagers (DeepSpar, PC-3000, etc.).
- Any decision to retire the drive or escalate to a professional lab.

---

## 2. Background: ddrescue concepts the harness depends on

The harness's logic is built entirely on three ddrescue facts. Get these right or the harness is unsafe.

### 2.1 The mapfile is the source of truth
ddrescue is always invoked as:

```
ddrescue [options] <infile> <outfile> <mapfile>
```

The **mapfile** (called *logfile* before v1.20) records, persistently and on disk, what has been recovered and what has not. It survives `SIGINT`, `SIGKILL`, and power loss, and it is what allows recovery to resume rather than restart. **The harness MUST always pass a mapfile and MUST never delete or truncate it.**

### 2.2 Block status characters
Every region in the mapfile carries a status character. The harness parses these to make decisions:

| Char | Meaning | Phase that acts on it |
|------|---------|-----------------------|
| `?`  | non-tried | copying |
| `*`  | non-trimmed (failed, awaiting trim) | trimming |
| `/`  | non-scraped (failed, awaiting scrape) | scraping |
| `-`  | bad-sector (failed after scrape) | retrying |
| `+`  | finished / recovered | — |
| `F` / `G` | filling / generating | (not used by this harness) |

The copying phase **only** acts on `?` blocks. This is the single most important fact for §8.

### 2.3 Mapfile structure
The mapfile is plain text with three parts: heading comments, a **status line**, and the **block list**.

- The status line is `current_pos current_status current_pass`. `current_status` is one of the characters above and reflects the phase ddrescue was last in.
- The block list is a series of `pos size status` lines (values in hex).

The harness reads both. It SHOULD use `ddrescuelog` for parsing rather than hand-rolling a parser where possible (see §12), but MUST be able to fall back to reading the raw block list, since `ddrescuelog` flag availability varies slightly across versions — **verify against `ddrescuelog --help` on the target system at startup.**

---

## 3. Recovery strategy (the algorithm the harness implements)

The harness implements a phased strategy. **Each phase runs to genuine completion before the next begins.**

1. **Phase A — Fast copy (`-n`), both directions.**
   Harvest every easily-readable sector while the drive is still alive, skipping all slow recovery work. This is where almost all recoverable data is obtained, and it is the phase the rest of this spec is mostly about.

2. **Phase B — Trim + scrape (no `-n`).**
   Only after Phase A is genuinely exhausted (§8), attack the remaining bad regions. For a drive that hangs hard enough to require power-cycling, Phase B is often low-yield and drive-stressing; it MUST be gated, time-boxed, and retry-limited by configuration (§11), and SHOULD default to a conservative retry count.

The rationale for ordering: a failing drive is racing its own death. Spending time scraping one bad region early means easily-readable data elsewhere may be lost as the drive degrades. Copy everything cheap first.

---

## 4. Harness state machine

```
        ┌─────────────┐
        │   STARTUP    │  verify config, tools, device identity, mapfile
        └──────┬───────┘
               │
               ▼
        ┌─────────────┐
        │  COPY_FWD    │◄──────────────┐
        │  (-n)        │               │
        └──────┬───────┘               │
               │ stall detected        │ power-cycled,
               ▼                       │ device re-verified
        ┌─────────────┐                │
        │ POWER_CYCLE  │────────────────┘
        └──────┬───────┘
               │ on relaunch after a stall, toggle direction
               ▼
        ┌─────────────┐
        │  COPY_REV    │  (-n -R)
        └──────┬───────┘
               │
               ▼
        ┌─────────────┐
        │ COPY_DONE?   │  §8 completion test
        └──────┬───────┘
          no ──┘ (resume alternating COPY_FWD / COPY_REV)
          yes
               ▼
        ┌─────────────┐
        │  TRIM_SCRAPE │  Phase B, gated by config
        └──────┬───────┘
               ▼
        ┌─────────────┐
        │   FINISHED   │  or ABORTED (budget/limit reached)
        └─────────────┘
```

States in detail:

- **STARTUP** — Validate configuration; confirm `ddrescue` and `ddrescuelog` versions; resolve and record the source device's **stable identity** (§10.1); create or validate the mapfile; back it up.
- **COPY_FWD / COPY_REV** — Run ddrescue in the `-n` copy mode, forward or reverse. Monitor for progress (§5). Exit the state on normal ddrescue exit **or** on stall detection.
- **POWER_CYCLE** — Terminate ddrescue if it is still alive, power-cycle the source device, wait for re-enumeration, re-verify identity, and decide the next state (toggle direction; decide whether `-A` is needed, §7).
- **COPY_DONE?** — Apply the §8 test. If not done, return to copying in the opposite direction from the last completed sweep.
- **TRIM_SCRAPE** — Phase B, only if enabled and within budget.
- **FINISHED / ABORTED** — Terminal. Emit a final report (§13).

---

## 5. Progress monitoring and hang detection

This is the core engineering problem and the reason the harness exists.

### 5.1 Why ddrescue's own `--timeout` is not sufficient
ddrescue's `--timeout` (`-T`) aborts if no successful read happens within an interval. It is useful for **slow but live** drives. It is **not** reliable for a true bus-level hang: when the device stops responding entirely, the ddrescue process blocks inside an uninterruptible `read()` syscall (kernel **D state**) and cannot run its own userspace timeout logic — and frequently cannot even be killed with `SIGKILL` until the pending I/O completes or errors out.

**Therefore the harness MUST detect stalls externally and MUST break them by removing power from the device, not by signalling ddrescue.**

The harness SHOULD still pass `--timeout` as a secondary safety net, but MUST NOT depend on it.

### 5.2 Progress source
The harness MUST track forward progress from a source independent of the ddrescue process's responsiveness. Acceptable sources, in order of preference:

1. **`--log-rates=<file>`** — ddrescue appends one line per second with timestamp, input position, current/average rates, bad-area count, and total error size. This is machine-readable and the recommended primary source. Note: a true hang means *no new line is appended*, so the harness watches the file's growth/mtime as well as its contents.
2. **Mapfile polling** — parse `current_pos` from the status line and the `rescued`/non-tried totals (via `ddrescuelog`, §12) on an interval. ddrescue saves the mapfile periodically (`--interval`, default ~30 s) and on exit.
3. **`/proc/<pid>/stat`** — read process state; a sustained `D` (uninterruptible sleep) state alongside no progress is a strong hang signal.

### 5.3 Stall definition
A **stall** is declared when **all** of the following hold for a configurable `STALL_WINDOW` (default 120 s):

- No increase in rescued bytes (from the progress source), **and**
- No advance in `current_pos`, **and**
- (if available) the process is in `D` state or `time since last successful read` is not advancing.

`STALL_WINDOW` MUST be longer than ddrescue's mapfile save interval and longer than expected worst-case single-read latency on a slow-but-live drive, to avoid power-cycling a drive that is merely crawling.

### 5.4 Stall response
On a declared stall the harness transitions to **POWER_CYCLE**:

1. Attempt graceful `SIGINT` to ddrescue (lets it flush the mapfile). Wait a short grace period.
2. If the process will not exit (D state), proceed anyway — the power cut will release the blocked I/O.
3. Cut power to the source device (§6).
4. Wait `POWER_OFF_DWELL` (default 15 s) for the device to fully spin down / capacitors to drain.
5. Restore power, wait for re-enumeration, then re-verify identity (§10.1).
6. If the process was still alive in D state, confirm it has now exited before relaunching.

---

## 6. Power-cycle control

The harness MUST be able to remove and restore power to the **source device** programmatically. The mechanism is environment-specific and MUST be pluggable behind an interface, e.g.:

```
interface PowerController {
    power_off()        // remove power from the source device
    power_on()         // restore power
    is_powered() -> bool
}
```

Reference implementations the developer may provide:
- **USB per-port power switching** via `uhubctl` (for USB-attached drives on supported hubs).
- **Managed PDU** (SNMP / HTTP API) for mains-powered enclosures.
- **GPIO/relay** controlling the drive's power rail.
- **Manual fallback** — prompt an operator and wait for confirmation. The harness MUST support a manual mode so it is usable without automated power hardware, degrading gracefully to "ask the human, then continue."

Requirements:
- `power_off` MUST cut power to the **drive**, not merely reset the USB data link (a data-only reset often does not clear a firmware hang).
- After `power_on`, the harness MUST NOT assume the previous device node (`/dev/sdX`) is valid (§10.1).

---

## 7. The non-tried demotion problem (`--try-again`)

This is a subtle trap specific to the hang/power-cycle workflow and MUST be handled explicitly.

When ddrescue is interrupted (kill or power loss) **while actively reading a block**, that block is typically recorded as **non-trimmed (`*`)**, not left as non-tried (`?`). Consequences:

- On relaunch, ddrescue sees no `?` in that region and may jump straight to **trimming/scraping** it — slow, drive-stressing work — even though the region was never genuinely attempted with a fast copy read. It was merely interrupted.
- The `non-tried` total can therefore reach zero **prematurely**, making the copy phase look complete when fast-readable data is still trapped in mislabeled `*`/`/` regions.

**Fix:** ddrescue's `-A` / `--try-again` marks all non-trimmed and non-scraped blocks inside the rescue domain back to non-tried before starting, so the next `-n` pass re-attempts them as fast copies.

Harness requirements:
- After a power-cycle that interrupted an active read, the harness SHOULD relaunch the **copy** pass with `-A` so interrupted regions are retried as fast copies rather than scraped.
- `-A` MUST be used **only during Phase A (copy)**. It MUST NOT be used once the harness has decided to enter Phase B (trim/scrape), or it will undo legitimate trim/scrape progress.
- The harness MUST track, in its own state, whether `-A` has already "re-promoted" a region in the current sweep, to avoid an infinite loop where every cycle re-promotes the same hang region (see §8.3 termination guard).

---

## 8. Determining copy-phase completion

The copy phase (Phase A) is complete when the **fast-readable data is exhausted** — not merely when `non-tried` momentarily reads zero.

### 8.1 Naive signal (necessary but not sufficient)
`non-tried == 0` in the mapfile (i.e., no `?` blocks remain). The harness reads this via `ddrescuelog` or by confirming the block list contains no `?` entries. Because of §7, this alone MUST NOT be treated as completion.

### 8.2 Completion criterion (required)
Phase A is considered **truly done** only when **both** of the following sweeps have run **to ddrescue's own normal completion** (not terminated by a stall) since the last `-A` re-promotion:

- a full **forward** `-n` pass, and
- a full **reverse** `-n -R` pass,

with `non-tried` remaining `0` across both. In other words: every region has been attempted as a fast read from at least one direction and resolved to either `+` (recovered) or a genuine failure state (`*` / `/` / `-`), and re-promoting interrupted blocks (`-A`) no longer yields any new `?` work.

### 8.3 Termination guard (required)
A drive can hang on the *same* region every cycle, and `-A` will keep re-promoting it, producing an infinite loop. The harness MUST cap this. Recommended guards (configurable, §11):

- `MAX_COPY_CYCLES` — absolute cap on power-cycle/relaunch iterations in Phase A.
- `MAX_REPROMOTE_PER_REGION` — if the same offset region is re-promoted via `-A` more than N times without progress, the harness MUST stop re-promoting it, leave it in its failed state, and either skip past it (`-i` to advance input position, or `-K` to enlarge skip size) or accept it as unrecoverable-by-copy.
- `GLOBAL_TIME_BUDGET` — wall-clock cap for Phase A.

When any guard trips, the harness records the region(s) as copy-unrecoverable and proceeds to the completion test with what remains.

### 8.4 Optional visualization
The harness SHOULD be able to emit the mapfile for inspection by a block-map visualizer (e.g. ddrescueview) and SHOULD include a textual block-map summary in its reports so an operator can see where unread regions remain.

---

## 9. Transition to trim/scrape (Phase B)

Phase B begins only after §8.2 is satisfied (or §8.3 guards tripped) **and** Phase B is enabled in configuration.

- Invoke ddrescue **without** `-n` and **without** `-A`.
- Apply a conservative, configurable retry count (`-r`, default small, e.g. `-r1` or `-r2`; never default to `-r-1`).
- Apply the same stall-detection and power-cycle machinery (§5–§6); a drive that hung in Phase A will hang harder here.
- Time-box Phase B (`PHASE_B_TIME_BUDGET`) and stop on budget, on `MAX_BAD_AREAS` growth, or on operator abort.
- Phase B MUST be skippable entirely via configuration, because for many hard-hanging drives it is not worth the additional stress.

---

## 10. Safety requirements

These are hard requirements. Violating any of them risks destroying the recovery or the source.

### 10.1 Device identity — never trust `/dev/sdX`
After any power-cycle or re-enumeration, the source's device node can change (`/dev/sdb` → `/dev/sdc`), and another drive could take the old name.

- The harness MUST resolve and pin the source by a **stable identifier** — `by-id` / WWN / model+serial (e.g. via `udevadm`, `/dev/disk/by-id/`, `lsblk -o NAME,SERIAL,WWN`).
- Before **every** relaunch, the harness MUST re-resolve the current node from the pinned identifier and confirm it matches. If the identifier cannot be found, the harness MUST pause (device not yet re-enumerated) or abort — it MUST NOT guess a node.
- The harness MUST refuse to start ddrescue if the resolved source node does not match the pinned identity.

### 10.2 Never swap infile/outfile
The harness MUST construct the ddrescue command line with source and destination in fixed, validated positions, and MUST verify the destination is **not** the source device and is at least as large as the source. An accidental swap is instantly destructive and irreversible.

### 10.3 Mapfile integrity
- The harness MUST keep a rolling **backup** of the mapfile before each relaunch (e.g. `mapfile.bak.<timestamp>`), so a corrupted or mis-specified mapfile can be recovered.
- The harness SHOULD `diff` the live mapfile against the previous backup after each cycle to confirm forward progress and to detect a stuck recovery.
- The harness MUST guard against using a mapfile from an unrelated job (validate the heading comment's recorded command line / device against the current run).

### 10.4 Destination writes
- If the destination is a **device** (not an image file), ddrescue requires `-f` / `--force`. The harness MUST set this only when the destination is a block device and only after the §10.2 checks pass.
- Direct disc access on the **source** (`-d` / `--idirect`) SHOULD be the default for failing hardware.

### 10.5 No write-back to the source
The source is mounted nowhere and is opened read-only by ddrescue in this workflow. The harness MUST verify the source is not mounted before starting and SHOULD set the kernel block device read-only (`blockdev --setro`) as defense in depth.

---

## 11. Configuration parameters

All tunables MUST be configurable (file and/or CLI). Suggested defaults in brackets.

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `SOURCE_ID` | (required) | Stable identifier of the source (WWN/serial/by-id). |
| `DEST_PATH` | (required) | Destination image file or device. |
| `MAPFILE_PATH` | (required) | Mapfile path. |
| `STALL_WINDOW` | 120 s | No-progress window before declaring a stall (§5.3). |
| `POWER_OFF_DWELL` | 15 s | Power-off dwell time (§5.4). |
| `REENUM_TIMEOUT` | 60 s | Max wait for device re-enumeration after power-on. |
| `MAX_COPY_CYCLES` | 50 | Cap on Phase A power-cycle iterations (§8.3). |
| `MAX_REPROMOTE_PER_REGION` | 3 | Cap on `-A` re-promotion per region (§8.3). |
| `GLOBAL_TIME_BUDGET` | 24 h | Wall-clock cap for Phase A. |
| `PHASE_B_ENABLED` | false | Whether to attempt trim/scrape (§9). |
| `PHASE_B_RETRIES` | 1 | ddrescue `-r` value in Phase B. |
| `PHASE_B_TIME_BUDGET` | 4 h | Wall-clock cap for Phase B. |
| `USE_IDIRECT` | true | Pass `-d` on the source. |
| `DDRESCUE_TIMEOUT` | 60 s | Secondary `-T` safety net (not relied upon). |
| `SKIP_SIZE` | unset | Optional `-K` value for jumping bad patches. |
| `POWER_CONTROLLER` | manual | Which PowerController implementation to use (§6). |

---

## 12. Command reference

The harness assembles ddrescue invocations from these building blocks. **Always** end with `<source-node> <dest> <mapfile>`.

Phase A, forward:
```
ddrescue -d -n [-T <DDRESCUE_TIMEOUT>] [--log-rates=<rates.log>] <src> <dest> <mapfile>
```

Phase A, reverse:
```
ddrescue -d -n -R [-T <DDRESCUE_TIMEOUT>] [--log-rates=<rates.log>] <src> <dest> <mapfile>
```

Phase A relaunch after an interrupting hang (re-promote interrupted blocks):
```
ddrescue -d -n -A [-R] <src> <dest> <mapfile>
```

Skip past a stubborn region (optional, §8.3):
```
ddrescue -d -n -K <SKIP_SIZE> <src> <dest> <mapfile>
# or advance the start position explicitly:
ddrescue -d -n -i <offset> <src> <dest> <mapfile>
```

Phase B (trim + scrape, conservative retries):
```
ddrescue -d -r <PHASE_B_RETRIES> <src> <dest> <mapfile>
```

Mapfile inspection (verify exact flags with `ddrescuelog --help` on the target — availability varies by version):
```
ddrescuelog -t <mapfile>     # size/percentage breakdown per status type
ddrescuelog -D <mapfile>     # exit status reflects whether all blocks are finished
```
The harness MUST be able to fall back to parsing the raw block list for `?` entries if a given `ddrescuelog` subcommand is unavailable.

Flag meanings used above:
- `-d` / `--idirect` — direct disc access (bypass cache).
- `-n` / `--no-scrape` — skip the scraping phase (Phase A fast copy).
- `-R` / `--reverse` — reverse the direction of all passes.
- `-A` / `--try-again` — mark non-trimmed/non-scraped blocks as non-tried (§7).
- `-r N` / `--retries` — retry passes in the retrying phase.
- `-T` / `--timeout` — exit if no successful read within interval (secondary net only).
- `-K` / `--skip-size`, `-i` / `--input-position` — skip/advance past bad regions.
- `-f` / `--force` — required when the destination is a device (§10.4).

> **Version note:** In ddrescue < 1.19, `-n` meant `--no-split`, not `--no-scrape`; before 1.20 the mapfile was called the *logfile*. The harness targets ≥ 1.22 and SHOULD assert the version at STARTUP and refuse to run on incompatible builds.

---

## 13. Logging and observability

The harness MUST produce, at minimum:

- A structured event log: every state transition, power-cycle, relaunch (with the exact command line), stall declaration, and guard trip, each timestamped.
- Per-cycle progress: rescued bytes, non-tried bytes, bad-area count, total error size, delta since previous cycle.
- The pinned device identity and the resolved node used for each launch.
- A final report on reaching FINISHED/ABORTED: total rescued vs. source size, percentage, count and locations of unrecovered regions, number of power cycles, total wall-clock, and which phase/guard terminated the run.

The harness SHOULD retain the `--log-rates` file and all mapfile backups as recovery artifacts.

---

## 14. Failure modes and edge cases

- **Process won't die in D state.** Expected; the power cut releases the blocked I/O. The harness MUST confirm process exit *after* power restoration, not before.
- **Device never re-enumerates** within `REENUM_TIMEOUT`. Pause and alert; do not relaunch against a missing or wrong node.
- **Old node reused by a different drive.** Prevented by §10.1 identity pinning; the harness MUST detect mismatch and refuse to run.
- **Mapfile says complete but `non-tried` was zeroed by demotion.** Handled by §7/§8.2; do not declare Phase A done on the naive signal alone.
- **Same region hangs forever.** Bounded by §8.3 guards.
- **Reverse pass balloons the output image to full size.** Expected and benign: reversing makes ddrescue write at high offsets, growing a sparse file. The harness MUST NOT treat sudden image-size growth as an error.
- **Destination fills up** (non-sparse target). The harness SHOULD check free space against source size at STARTUP and consider preallocation.
- **Operator abort.** The harness MUST handle a clean shutdown signal by flushing/preserving the mapfile and exiting without corrupting state.

---

## 15. Non-goals

- The harness does not interpret or repair the recovered filesystem.
- It does not make the clinical call that the drive should go to a hardware lab; it surfaces the data needed for a human to decide.
- It does not attempt to defeat firmware-level lockups beyond power-cycling.
- It is not a general-purpose imaging tool for healthy media.

---

## Appendix A — One-paragraph summary for reviewers

The harness runs ddrescue in a fast **copy-only** mode (`-n`) and alternates **forward** and **reverse** (`-R`) sweeps. Because a hanging drive blocks ddrescue in an uninterruptible state that its own `--timeout` cannot escape, the harness detects stalls **externally** (via `--log-rates`/mapfile/`/proc`) and breaks them by **power-cycling the drive**, then re-verifies device identity by stable ID before relaunching. Interrupted reads get demoted to non-trimmed in the mapfile, so the harness uses `--try-again` (`-A`) to re-promote them to non-tried and re-attempt them as fast copies, with guards against infinite re-promotion. The copy phase is declared done only when a full forward and a full reverse sweep both complete normally with zero non-tried left. Only then, and only if enabled, does it attempt the slow, conservative trim/scrape phase.
