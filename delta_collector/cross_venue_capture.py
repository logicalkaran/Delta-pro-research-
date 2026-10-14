"""Compatibility entrypoint for the research-only cross-venue archive capture.

This module performs public market-data capture only. It does not trade or touch
production strategy, risk, or execution modules.
"""
import argparse
from research import cross_venue_aligned_capture_v1 as capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=int, default=600)
    parser.add_argument('--archive-only', action='store_true')
    args = parser.parse_args()
    capture.main_args = ['--duration-seconds', str(args.duration)] + (['--archive-only'] if args.archive_only else [])
    import sys
    old_argv = sys.argv
    try:
        sys.argv = [old_argv[0], *capture.main_args]
        capture.main()
    finally:
        sys.argv = old_argv

if __name__ == '__main__': main()
