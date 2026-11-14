"""Export a frequency vocabulary locally using the optional wordfreq package."""

import argparse
import csv
from importlib.metadata import version
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New output TSV; existing files are never replaced")
    parser.add_argument("--words", type=int, default=50000, help="Number of frequency-list entries to inspect")
    args = parser.parse_args()
    if not 1 <= args.words <= 500000:
        parser.error("--words must be between 1 and 500000")
    try:
        from wordfreq import top_n_list, word_frequency
    except ImportError:
        parser.exit(1, "Install the optional dependency first: python3 -m pip install wordfreq==3.1.1\n")
    try:
        words = top_n_list("en", args.words)
        entries = [(word, word_frequency(word, "en")) for word in words if re.fullmatch(r"[a-z]+", word)]
        with args.output.open("x", newline="") as file:
            file.write(f"# Source: wordfreq {version('wordfreq')}, English; inspect source licenses before redistributing.\n")
            writer = csv.writer(file, delimiter="\t")
            writer.writerow(["word", "weight"])
            writer.writerows((word, weight) for word, weight in entries if weight > 0)
        print(f"Wrote {sum(weight > 0 for _, weight in entries)} ASCII words to {args.output}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not build lexicon: {error}\n")


if __name__ == "__main__":
    main()
