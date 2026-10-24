"""Runs the evaluation suites and writes eval/RESULTS.md.

Suites are added as their stages exist. A suite that cannot run yet is
listed as not run, never given a number.
"""

from pathlib import Path

SUITES = ["Authoring", "Touch", "Latency", "Voice", "Answers", "User"]


def main() -> None:
    out = Path(__file__).with_name("RESULTS.md")
    lines = ["# Eval results", "", "| Suite | Status |", "|---|---|"]
    lines += [f"| {name} | not run |" for name in SUITES]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
