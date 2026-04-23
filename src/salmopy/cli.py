"""Command-line interface for inSTREAM simulations."""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Salmopy-py salmonid simulation")
    parser.add_argument("config", help="Path to YAML configuration file")
    parser.add_argument(
        "--data-dir",
        help="Directory containing data files (default: config file's parent)",
    )
    parser.add_argument("--output-dir", "-o", help="Directory for output files")
    parser.add_argument("--end-date", help="Override end date (YYYY-MM-DD)")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress progress output"
    )
    args = parser.parse_args()

    from salmopy.model import SalmopyModel

    config_path = Path(args.config)
    if not config_path.exists():
        print("Error: config file not found: {}".format(config_path), file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print("Loading model from {}...".format(config_path))

    model = SalmopyModel(
        config_path,
        data_dir=args.data_dir,
        end_date_override=args.end_date,
    )

    if not args.quiet:
        print("  Species: {}".format(model.species_order))
        print("  Reaches: {}".format(model.reach_order))
        print("  Cells: {}".format(model.fem_space.num_cells))
        print("  Fish: {}".format(model.trout_state.num_alive()))
        print("Running simulation...")

    step_count = 0
    while not model.time_manager.is_done():
        model.step()
        step_count += 1
        if not args.quiet and step_count % 100 == 0:
            print(
                "  Day {}: {} fish alive".format(
                    step_count, model.trout_state.num_alive()
                )
            )

    if not args.quiet:
        print(
            "Simulation complete: {} days, {} fish alive".format(
                step_count, model.trout_state.num_alive()
            )
        )

    if args.output_dir:
        model.write_outputs(args.output_dir)
        if not args.quiet:
            print("Output written to {}".format(args.output_dir))


if __name__ == "__main__":
    main()
