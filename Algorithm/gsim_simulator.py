#!/usr/bin/env python3
"""
GSIM SOR Simulator
==================
Solves Ax = b using Successive Over-Relaxation (SOR) with omega = 1.25,
matching the GSIM hardware implementation exactly.

Matrix A is a fixed 16x16 banded matrix:
  diagonal=20, offset±1=-13, offset±2=+6, offset±3=-1

Usage
-----
  # Single pattern file, fixed iterations:
  python gsim_simulator.py pattern1.dat 30

  # Single pattern file, iterate until E² < 1e-6 (Rank A):
  python gsim_simulator.py pattern1.dat

  # Enumerate all 10^16 permutations of 10 evenly-spaced b values, fixed iters:
  python gsim_simulator.py --iterations 30

  # Enumerate permutations, convergence mode:
  python gsim_simulator.py

Options
-------
  --iterations N    Fixed iteration count  (overrides positional argument)
  --max-iter N      Safety cap for convergence mode [default: 10000]
  --quiet           Condensed single-line output per vector
  --checkpoint F    Path to checkpoint file [default: gsim_checkpoint.json]
  --progress N      Print progress every N vectors in permutation mode [default: 100000]
"""

import argparse
import sys
import os
import json
import math
import itertools
import glob
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
N = 16                     # System size
OMEGA = 1.25               # SOR relaxation factor
INV16 = 1.0 / 16.0        # omega / diagonal = 1.25 / 20 = 1/16
ONE_MINUS_OMEGA = -0.25    # 1 - omega
LEVEL_A_THRESHOLD = 1e-6   # E² < 1e-6  →  Rank A (PASS)
MAX_ITER_DEFAULT = 10_000  # Safety cap for convergence mode
CHECKPOINT_DEFAULT = 100_000
CHUNK_SIZE_DEFAULT = 2048

# Score level boundaries from testfixture1.v (upper-exclusive thresholds)
SCORE_LEVELS: List[Tuple[float, str, bool]] = [
    (1e-6,   "A", True),
    (5e-6,   "B", True),
    (1e-5,   "C", True),
    (5e-5,   "D", True),
    (1e-4,   "E", True),
    (1e-3,   "F", True),
    (5e-3,   "G", True),
    (1e-2,   "H", True),
    (1e-1,   "I", True),
    (3e-1,   "J", True),
    (math.inf, "K", False),
]

# ---------------------------------------------------------------------------
# Matrix A  (16x16, banded)
# ---------------------------------------------------------------------------
# Constructed from testfixture1.v Mb[] expressions.
# Row i: A[i][j] is non-zero for j in {i-3..i+3}
#   offset 0: +20
#   offset ±1: -13
#   offset ±2: +6
#   offset ±3: -1

def _build_matrix_a() -> List[List[float]]:
    A = [[0.0] * N for _ in range(N)]
    offsets = {0: 20.0, 1: -13.0, 2: 6.0, 3: -1.0}
    for i in range(N):
        for d, coeff in offsets.items():
            A[i][i] = offsets[0]            # diagonal (re-set each row is fine)
        for d in (1, 2, 3):
            coeff = offsets[d]
            if i + d < N:
                A[i][i + d] = coeff
            if i - d >= 0:
                A[i][i - d] = coeff
    return A

A_MATRIX = _build_matrix_a()

# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def to_signed16(raw: int) -> int:
    """Interpret 16-bit unsigned integer as 16-bit 2's complement signed."""
    raw &= 0xFFFF
    return raw if raw < 0x8000 else raw - 0x10000


def float_to_q16_16(value: float) -> int:
    """
    Convert a Python float to 32-bit signed Q16.16 fixed-point integer
    (matching the GSIM hardware output format).
    Returns an unsigned 32-bit integer (use 0x prefix when displaying).
    """
    raw = round(value * 65536.0)
    # Clamp to 32-bit signed range
    raw = max(-(1 << 31), min((1 << 31) - 1, raw))
    # Return as unsigned 32-bit for hex display
    return raw & 0xFFFFFFFF


def q16_16_to_float(raw32: int) -> float:
    """
    Convert a 32-bit unsigned Q16.16 integer back to float
    (replicates testbench: if bit31==1 → negate two's complement then /65536).
    """
    raw32 &= 0xFFFFFFFF
    if raw32 & 0x80000000:
        signed = raw32 - 0x100000000
    else:
        signed = raw32
    return signed / 65536.0

# ---------------------------------------------------------------------------
# SOR iteration engine
# ---------------------------------------------------------------------------

def sor_iterate(b: List[int], x: List[float]) -> List[float]:
    """
    Perform one SOR iteration with omega = 1.25 using Gauss-Seidel ordering.

    Formula for each i (0-indexed):
        x_new[i] = (1 - omega) * x[i]
                 + (omega / a_ii) * (b[i]
                   + 13*(x_upper1 + x_lower1)
                   -  6*(x_upper2 + x_lower2)
                   +  1*(x_upper3 + x_lower3))

    Where:
        x_upper_k = x[i+k] from previous iteration (not yet updated)
        x_lower_k = x_new[i-k] already updated this iteration
        (boundary: index outside [0,N-1] → 0.0)

    Simplification: omega/20 = 1.25/20 = 1/16
                    1 - omega = -0.25
    """
    x_new = x[:]

    for i in range(N):
        def _get(j: int) -> float:
            """Fetch x value with Gauss-Seidel ordering and boundary zeroing."""
            if j < 0 or j >= N:
                return 0.0
            return x_new[j] if j < i else x[j]

        gs_sum = (float(b[i])
                  + 13.0 * (_get(i + 1) + _get(i - 1))
                  -  6.0 * (_get(i + 2) + _get(i - 2))
                  +  1.0 * (_get(i + 3) + _get(i - 3)))

        x_new[i] = ONE_MINUS_OMEGA * x[i] + INV16 * gs_sum

    return x_new


def compute_mb(x: List[float]) -> List[float]:
    """Compute Mb = A * x (exact matrix multiply, verified against testfixture1.v)."""
    mb = [0.0] * N
    for i in range(N):
        for j in range(N):
            mb[i] += A_MATRIX[i][j] * x[j]
    return mb


def compute_e2(b: List[int], x: List[float]) -> float:
    """
    Compute E² = sum((Mb_i - b_i)²) as per testfixture1.v grading logic.

    Testbench logic (equivalent to Mb[i] - b_signed[i] in all cases):
      if b[j][15]==1:  error = |b[j]| + Mb[j]   # b negative → adds magnitude
      else:            error = Mb[j] - b[j]       # b positive → subtracts
    Both forms equal Mb[i] - b_signed[i].
    """
    mb = compute_mb(x)
    return sum((mb[i] - float(b[i])) ** 2 for i in range(N))


def get_level(e2: float) -> Tuple[str, bool]:
    """Return (level_letter, passed) for a given E² value."""
    for threshold, level, passed in SCORE_LEVELS:
        if e2 < threshold:
            return level, passed
    return "K", False  # unreachable but safe


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------

def simulate(b: List[int],
             num_iter: Optional[int],
             max_iter: int = MAX_ITER_DEFAULT) -> dict:
    """
    Run SOR simulation for a given b vector.

    Parameters
    ----------
    b        : 16 signed integers (input vector)
    num_iter : exact iteration count, or None for convergence mode
    max_iter : safety cap used only in convergence mode

    Returns
    -------
    dict with keys: b, x_float, x_hex, e2, level, passed, iterations
    """
    x = [0.0] * N

    if num_iter is not None:
        # Fixed-iteration mode
        for _ in range(num_iter):
            x = sor_iterate(b, x)
        e2 = compute_e2(b, x)
        iters_done = num_iter
    else:
        # Convergence mode: iterate until E² < Rank-A threshold or cap
        e2 = compute_e2(b, x)
        iters_done = 0
        while e2 >= LEVEL_A_THRESHOLD and iters_done < max_iter:
            x = sor_iterate(b, x)
            e2 = compute_e2(b, x)
            iters_done += 1

    level, passed = get_level(e2)

    # Convert to Q16.16 (hardware output format)
    x_q16 = [float_to_q16_16(xi) for xi in x]
    x_hex  = [f"0x{v:08X}" for v in x_q16]

    return {
        "b":         b,
        "x_float":   x,
        "x_hex":     x_hex,
        "e2":        e2,
        "level":     level,
        "passed":    passed,
        "iterations": iters_done,
    }


# ---------------------------------------------------------------------------
# Input parser
# ---------------------------------------------------------------------------

def parse_pattern_file(path: str) -> List[int]:
    """
    Parse a GSIM .dat pattern file.
    Format: 16 lines of 4-digit hex (16-bit), optional '// comment' suffix.
    Returns list of 16 signed integers.
    """
    b: List[int] = []
    with open(path, "r") as fh:
        for raw_line in fh:
            line = raw_line.split("//")[0].strip()
            if not line:
                continue
            try:
                b.append(to_signed16(int(line, 16)))
            except ValueError:
                raise ValueError(f"Unparseable hex token: '{line}' in {path}")
    if len(b) != N:
        raise ValueError(f"Expected {N} b-values in {path}, got {len(b)}")
    return b


# ---------------------------------------------------------------------------
# Output / reporting
# ---------------------------------------------------------------------------

GOLDEN_X1 = [
    402.1120217501,  1689.5336804421, 2455.4774264763,  563.1671481130,
    703.0136705772,  1745.1919122734,   33.2002351074,  607.1379155812,
   -477.5895727426,  869.0943789319,  1907.5237775384, 1524.3408800767,
    596.4154551345,  1476.6345624265, 1011.5707976786, -1330.8985774801,
]


def print_result(result: dict, quiet: bool = False, show_golden: bool = False) -> None:
    """Print simulation results in a human-readable format."""
    e2    = result["e2"]
    level = result["level"]
    ok    = result["passed"]

    if quiet:
        print(f"iters={result['iterations']:5d}  E²={e2:.6e}  Level={level}  "
              f"{'PASS' if ok else 'FAIL'}")
        return

    print()
    print("=" * 68)
    print(f"  Iterations run : {result['iterations']}")
    print(f"  E²             : {e2:.15e}")
    print(f"  Score Level    : {level}  ({'PASS ✓' if ok else 'FAIL ✗'})")
    print(f"  Rank A (E²<1e-6): {'YES ✓' if e2 < LEVEL_A_THRESHOLD else 'NO  ✗'}")
    print("=" * 68)

    hdr = f"  {'i':>3}  {'x (float)':>22}  {'Q16.16 hex':>12}"
    if show_golden:
        hdr += f"  {'golden':>22}  {'Δ':>12}"
    print(hdr)
    print("  " + "-" * (64 if show_golden else 40))

    for i, (xf, xh) in enumerate(zip(result["x_float"], result["x_hex"])):
        row = f"  x{i+1:>2}  {xf:>22.10f}  {xh:>12}"
        if show_golden:
            g   = GOLDEN_X1[i]
            row += f"  {g:>22.10f}  {abs(xf - g):>12.6f}"
        print(row)
    print()


# ---------------------------------------------------------------------------
# Permutation mode
# ---------------------------------------------------------------------------

def _evenly_spaced_b_values() -> List[int]:
    """
    Generate 10 evenly spaced 16-bit signed integers from -32768 to 32767.
    Step = (32767 - (-32768)) / 9 ≈ 7279.44, rounded to nearest integer.
    """
    lo, hi = -32768, 32767
    return [round(lo + i * (hi - lo) / 9) for i in range(10)]


def _load_checkpoint(path: str) -> int:
    """Return the index to resume from (0 if no checkpoint exists)."""
    if os.path.exists(path):
        try:
            with open(path) as fh:
                return int(json.load(fh).get("next_index", 0))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return 0


def _save_checkpoint(path: str, next_index: int) -> None:
    with open(path, "w") as fh:
        json.dump({"next_index": next_index}, fh)


def _simulate_permutation_case(args: Tuple[Tuple[int, ...], List[int], Optional[int], int]) -> Tuple[str, bool, bool]:
    """Worker helper for threaded permutation execution."""
    indices, perm_vals, num_iter, max_iter = args
    b = [perm_vals[k] for k in indices]
    result = simulate(b, num_iter, max_iter)
    level = result["level"]
    passed = result["passed"]
    return level, passed, (level == "A")


def run_permutation_mode(num_iter:   Optional[int],
                         max_iter:   int,
                         ckpt_path:  str,
                         progress_n: int,
                         workers: int,
                         chunk_size: int) -> None:
    """
    Enumerate ALL 10^16 b-vectors formed by the Cartesian product of
    10 evenly spaced values, simulate each, and report aggregate statistics.

    Checkpointing: saves current index every `progress_n` vectors so the run
    can be resumed after interruption by re-running with the same checkpoint file.
    """
    perm_vals = _evenly_spaced_b_values()
    total     = 10 ** N                          # 10^16
    start_idx = _load_checkpoint(ckpt_path)

    print()
    print("!" * 68)
    print("  PERMUTATION MODE")
    print(f"  Total vectors        : {total:.2e}  (10^{N})")
    print(f"  b element values     : {perm_vals}")
    print(f"  Resuming from index  : {start_idx:,}")
    print(f"  Checkpoint file      : {ckpt_path}")
    print(f"  Progress every       : {progress_n:,} vectors")
    print(f"  Worker threads       : {workers}")
    print(f"  Thread chunk size    : {chunk_size:,}")
    print("!" * 68)
    print()

    # Level counters
    level_counts = {lvl: 0 for _, lvl, _ in SCORE_LEVELS}
    pass_count   = 0
    rank_a_count = 0

    # Lazy Cartesian product, skipped to start_idx using islice
    gen = itertools.islice(itertools.product(range(10), repeat=N), start_idx, None)

    processed = 0
    if workers <= 1:
        for indices in gen:
            level, passed, is_rank_a = _simulate_permutation_case(
                (indices, perm_vals, num_iter, max_iter)
            )
            level_counts[level] += 1
            if passed:
                pass_count += 1
            if is_rank_a:
                rank_a_count += 1

            processed += 1
            abs_idx = start_idx + processed
            if processed % progress_n == 0:
                _save_checkpoint(ckpt_path, abs_idx)
                pct = abs_idx / total * 100
                print(f"  [{abs_idx:>20,} / {total:,}] ({pct:.6f}%)"
                      f"  PASS: {pass_count:,}  Rank A: {rank_a_count:,}")
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while True:
                chunk = list(itertools.islice(gen, chunk_size))
                if not chunk:
                    break

                work_items = (
                    (indices, perm_vals, num_iter, max_iter) for indices in chunk
                )
                for level, passed, is_rank_a in executor.map(_simulate_permutation_case, work_items):
                    level_counts[level] += 1
                    if passed:
                        pass_count += 1
                    if is_rank_a:
                        rank_a_count += 1

                    processed += 1
                    abs_idx = start_idx + processed
                    if processed % progress_n == 0:
                        _save_checkpoint(ckpt_path, abs_idx)
                        pct = abs_idx / total * 100
                        print(f"  [{abs_idx:>20,} / {total:,}] ({pct:.6f}%)"
                              f"  PASS: {pass_count:,}  Rank A: {rank_a_count:,}")

    # Final summary
    print()
    print("=" * 68)
    print("  PERMUTATION COMPLETE")
    print(f"  Vectors processed : {total:,}")
    print(f"  PASS              : {pass_count:,}")
    print(f"  Rank A (E²<1e-6)  : {rank_a_count:,}")
    print(f"  Level distribution:")
    for _, lvl, _ in SCORE_LEVELS:
        print(f"    {lvl} : {level_counts[lvl]:,}")
    print("=" * 68)
    print()

    # Clean up checkpoint on successful completion
    if os.path.exists(ckpt_path):
        os.remove(ckpt_path)
        print(f"  Checkpoint file removed: {ckpt_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gsim_simulator.py",
        description=(
            "GSIM SOR Simulator — solves 16×16 Ax=b using SOR (ω=1.25).\n\n"
            "FILE MODE:        gsim_simulator.py <pattern.dat> [N_ITERS]\n"
            "CONVERGENCE MODE: gsim_simulator.py <pattern.dat>\n"
            "PERMUTATION MODE: gsim_simulator.py  (no file — 10^16 vectors)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "input",
        nargs="?",
        default=None,
        metavar="PATTERN_FILE_OR_DIR",
        help=(
            "Path to a .dat file or a directory containing .dat files. "
            "Omit to enumerate all 10^16 permutations of 10 evenly-spaced values."
        ),
    )
    p.add_argument(
        "iterations",
        nargs="?",
        type=int,
        default=None,
        metavar="N_ITERS",
        help=(
            "Exact number of SOR iterations to run. "
            "Omit to iterate until E² < 1e-6 (Rank A), capped by --max-iter."
        ),
    )
    p.add_argument(
        "--iterations",
        dest="iterations_flag",
        type=int,
        default=None,
        metavar="N",
        help="Alternative flag for iteration count (overrides positional argument).",
    )
    p.add_argument(
        "--max-iter",
        type=int,
        default=MAX_ITER_DEFAULT,
        metavar="N",
        help=f"Max iterations for convergence mode safety cap [default: {MAX_ITER_DEFAULT}].",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Print condensed single-line output per vector.",
    )
    p.add_argument(
        "--golden",
        action="store_true",
        help="Show golden reference values alongside output (pattern1 only).",
    )
    p.add_argument(
        "--checkpoint",
        default="gsim_checkpoint.json",
        metavar="FILE",
        help="Checkpoint file path for permutation mode [default: gsim_checkpoint.json].",
    )
    p.add_argument(
        "--progress",
        type=int,
        default=CHECKPOINT_DEFAULT,
        metavar="N",
        help=f"Print progress every N vectors in permutation mode [default: {CHECKPOINT_DEFAULT}].",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Worker thread count for independent test cases [default: 1].",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE_DEFAULT,
        metavar="N",
        help=f"Thread work chunk size for permutation mode [default: {CHUNK_SIZE_DEFAULT}].",
    )
    return p


def _collect_pattern_files(path: str) -> List[str]:
    """Return sorted pattern file list from a file path or directory path."""
    if os.path.isfile(path):
        return [path]
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "pattern*.dat")))
        if not files:
            files = sorted(glob.glob(os.path.join(path, "*.dat")))
        return files
    return []


def _simulate_pattern_path(args: Tuple[str, Optional[int], int]) -> Tuple[str, dict]:
    """Worker helper for threaded pattern-file execution."""
    path, iters, max_iter = args
    b = parse_pattern_file(path)
    return path, simulate(b, iters, max_iter)


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if args.workers < 1:
        print("Error: --workers must be >= 1", file=sys.stderr)
        sys.exit(1)
    if args.chunk_size < 1:
        print("Error: --chunk-size must be >= 1", file=sys.stderr)
        sys.exit(1)
    if args.progress < 1:
        print("Error: --progress must be >= 1", file=sys.stderr)
        sys.exit(1)

    # --iterations flag overrides positional argument
    iters = args.iterations_flag if args.iterations_flag is not None else args.iterations

    if args.input is not None:
        # ── File mode ──────────────────────────────────────────────────────
        pattern_files = _collect_pattern_files(args.input)
        if not pattern_files:
            print(f"Error: no pattern file(s) found at: {args.input}", file=sys.stderr)
            sys.exit(1)

        if len(pattern_files) == 1:
            path = pattern_files[0]
            b = parse_pattern_file(path)
            result = simulate(b, iters, args.max_iter)

            if args.quiet:
                print_result(result, quiet=True)
            else:
                print(f"\n  Pattern file : {path}")
                if iters is not None:
                    print(f"  Mode         : fixed {iters} iteration(s)")
                else:
                    print(f"  Mode         : convergence (cap={args.max_iter})")
                print_result(result, quiet=False, show_golden=args.golden)
        else:
            print(f"\n  Multi-pattern mode: {len(pattern_files)} test cases")
            print(f"  Worker threads    : {args.workers}")

            jobs = ((path, iters, args.max_iter) for path in pattern_files)
            if args.workers <= 1:
                results = [_simulate_pattern_path(job) for job in jobs]
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    results = list(executor.map(_simulate_pattern_path, jobs))

            for path, result in results:
                if args.quiet:
                    print(f"{os.path.basename(path)}:", end=" ")
                    print_result(result, quiet=True)
                else:
                    print(f"\n  Pattern file : {path}")
                    if iters is not None:
                        print(f"  Mode         : fixed {iters} iteration(s)")
                    else:
                        print(f"  Mode         : convergence (cap={args.max_iter})")
                    print_result(result, quiet=False, show_golden=False)

    else:
        # ── Permutation mode ───────────────────────────────────────────────
        if iters is None:
            print(
                "  Permutation + convergence mode: each vector runs until "
                f"E² < 1e-6 or {args.max_iter} iterations.",
                file=sys.stderr,
            )
        run_permutation_mode(
            iters,
            args.max_iter,
            args.checkpoint,
            args.progress,
            args.workers,
            args.chunk_size,
        )


if __name__ == "__main__":
    main()
