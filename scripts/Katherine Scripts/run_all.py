#!/usr/bin/env python3
"""
Master script to run all data collection and analysis.

Usage:
    python run_all.py                  # Run everything
    python run_all.py --skip-arb      # Skip arbitration fetching
    python run_all.py --skip-rfc      # Skip RfC fetching
    python run_all.py --analyze-only  # Only run analysis on existing data
"""

import sys
import argparse
import subprocess
from pathlib import Path


def run_script(script_path: Path, description: str) -> bool:
    """
    Run a Python script and handle errors.
    
    Args:
        script_path: Path to the script
        description: Description for user
    
    Returns:
        True if successful, False otherwise
    """
    print("\n" + "=" * 70)
    print(f"RUNNING: {description}")
    print("=" * 70)
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            capture_output=False
        )
        print(f"\n✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ ERROR: {description} failed")
        print(f"  Exit code: {e.returncode}")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {description} failed with exception")
        print(f"  {str(e)}")
        return False


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Run Wikipedia dispute data collection and analysis"
    )
    parser.add_argument(
        '--skip-arb',
        action='store_true',
        help='Skip arbitration case fetching'
    )
    parser.add_argument(
        '--skip-rfc',
        action='store_true',
        help='Skip RfC fetching'
    )
    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='Only run analysis (requires existing data)'
    )
    
    args = parser.parse_args()
    
    scripts_dir = Path(__file__).parent / "scripts"
    
    print("=" * 70)
    print("Wikipedia Dispute Resolution Data Collection & Analysis")
    print("=" * 70)
    
    results = []
    
    # Step 1: Fetch Arbitration Cases
    if not args.skip_arb and not args.analyze_only:
        success = run_script(
            scripts_dir / "fetch_arbitration_cases.py",
            "Fetch Arbitration Cases"
        )
        results.append(("Arbitration Cases", success))
    
    # Step 2: Fetch RfCs
    if not args.skip_rfc and not args.analyze_only:
        success = run_script(
            scripts_dir / "fetch_requests_for_comments.py",
            "Fetch Requests for Comments"
        )
        results.append(("Requests for Comments", success))
    
    # Step 3: Analyze Relationships
    success = run_script(
        scripts_dir / "analyze_case_rfc_relationships.py",
        "Analyze Case-RfC Relationships"
    )
    results.append(("Analysis", success))
    
    # Print summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    
    for task, success in results:
        status = "✓ SUCCESS" if success else "✗ FAILED"
        print(f"{status}: {task}")
    
    all_success = all(success for _, success in results)
    
    if all_success:
        print("\n🎉 All tasks completed successfully!")
        print("\nYour data is ready in the data/raw/ directory:")
        print("  - data/raw/arbitration/")
        print("  - data/raw/rfc/")
        print("  - data/raw/analysis/")
    else:
        print("\n⚠️  Some tasks failed. Please check the errors above.")
        sys.exit(1)
    
    print("=" * 70)


if __name__ == "__main__":
    main()
