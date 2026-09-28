"""Command-line interface for corpus generation."""

import argparse
from pathlib import Path
from tracepaper.corpus.generator import CorpusGenerator


def main():
    """Main entry point for corpus generation."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic test corpus for Tracepaper"
    )
    parser.add_argument(
        "--items-per-control",
        type=int,
        default=3,
        help="Number of items per control (default: 3 for sample, 40 for full)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="corpus_data",
        help="Output directory for corpus files",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Generate full corpus (40 items per control) instead of sample",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Print schema and exit",
    )

    args = parser.parse_args()

    # Use appropriate default based on full flag
    if args.full:
        items_per_control = 40
        output_filename = "corpus_full.json"
    else:
        items_per_control = args.items_per_control
        output_filename = "corpus_sample.json"

    gen = CorpusGenerator(seed=args.seed, output_dir=args.output_dir)

    # Print schema
    gen.print_label_schema()

    if args.schema_only:
        return

    # Generate corpus
    print(f"\nGenerating {items_per_control * 3} total items ({items_per_control} per control)...\n")
    corpus = gen.generate_sample_corpus(items_per_control=items_per_control)

    # Print summary
    gen.print_summary(corpus)

    # Save
    gen.save_corpus(corpus, filename=output_filename)


if __name__ == "__main__":
    main()
