#!/usr/bin/env python3
"""
Unified CLI for Wikipedia dispute data collection and analysis.

This script orchestrates the collection of arbitration cases and RfCs,
then performs analysis to map relationships and identify patterns.

Usage:
    python run_dispute_collection.py --all              # Run everything
    python run_dispute_collection.py --collect          # Just collect data
    python run_dispute_collection.py --analyze          # Just analyze existing data
    python run_dispute_collection.py --arb              # Only arbitration cases
    python run_dispute_collection.py --rfc              # Only RfCs
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime


def run_command(cmd: list, description: str) -> bool:
    """Run a command and report results."""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"{'='*70}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed with error code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"✗ Command not found: {' '.join(cmd)}")
        return False


def check_environment():
    """Check if environment is properly configured."""
    print("Checking environment...")
    
    # Check for access token
    token = os.getenv('WIKIPEDIA_ACCESS_TOKEN')
    if token:
        print("  ✓ WIKIPEDIA_ACCESS_TOKEN found")
    else:
        print("  ⚠ WIKIPEDIA_ACCESS_TOKEN not set (may hit rate limits)")
    
    # Check for required Python
    print(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Wikipedia dispute data collection and analysis pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all                    # Run complete pipeline
  %(prog)s --collect                # Collect all data
  %(prog)s --analyze                # Analyze existing data
  %(prog)s --arb --limit 100        # Fetch first 100 arbitration cases
  %(prog)s --rfc --limit 50         # Fetch first 50 RfCs per category
        """
    )
    
    # Action flags
    parser.add_argument('--all', action='store_true',
                       help='Run complete pipeline (collect + analyze)')
    parser.add_argument('--collect', action='store_true',
                       help='Collect data (arb + rfc)')
    parser.add_argument('--analyze', action='store_true',
                       help='Analyze existing data')
    parser.add_argument('--arb', action='store_true',
                       help='Fetch arbitration cases only')
    parser.add_argument('--rfc', action='store_true',
                       help='Fetch RfCs only')
    
    # Options
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit number of items to fetch (per category for RfCs)')
    parser.add_argument('--output-dir', type=str, default='.',
                       help='Output directory for results (default: current directory)')
    
    args = parser.parse_args()
    
    # Default to --all if no flags specified
    if not any([args.all, args.collect, args.analyze, args.arb, args.rfc]):
        args.all = True
    
    # Determine what to run
    run_arb = args.all or args.collect or args.arb
    run_rfc = args.all or args.collect or args.rfc
    run_analysis = args.all or args.analyze
    
    # Start
    print("="*70)
    print("WIKIPEDIA DISPUTE DATA COLLECTION & ANALYSIS")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    check_environment()
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    results = []
    
    # Collect arbitration cases
    if run_arb:
        cmd = [sys.executable, 'fetch_all_arbitration.py']
        if args.limit:
            cmd.extend(['--limit', str(args.limit)])
        cmd.extend(['--output', os.path.join(args.output_dir, 'arbitration_cases_full.json')])
        
        success = run_command(cmd, "Fetching arbitration cases")
        results.append(('Arbitration cases', success))
    
    # Collect RfCs
    if run_rfc:
        cmd = [sys.executable, 'fetch_all_rfc.py']
        if args.limit:
            cmd.extend(['--limit', str(args.limit)])
        cmd.extend(['--output', os.path.join(args.output_dir, 'requests_for_comment_full.json')])
        
        success = run_command(cmd, "Fetching requests for comment")
        results.append(('Requests for comment', success))
    
    # Run analysis
    if run_analysis:
        cmd = [
            sys.executable, 'analyze_arb_rfc_mapping.py',
            '--arb', os.path.join(args.output_dir, 'arbitration_cases_full.json'),
            '--rfc', os.path.join(args.output_dir, 'requests_for_comment_full.json'),
            '--output', os.path.join(args.output_dir, 'arb_rfc_mapping.json'),
            '--report', os.path.join(args.output_dir, 'arb_rfc_report.txt')
        ]
        
        success = run_command(cmd, "Analyzing arbitration to RfC mapping")
        results.append(('Analysis', success))
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for task, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {task}")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Exit with error code if any task failed
    if any(not success for _, success in results):
        sys.exit(1)


if __name__ == '__main__':
    main()
