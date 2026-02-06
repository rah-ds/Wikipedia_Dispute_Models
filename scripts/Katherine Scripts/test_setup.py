#!/usr/bin/env python3
"""
Test script to verify the Wikipedia dispute collection toolkit.

This runs a small test collection to ensure everything is working.
"""

import subprocess
import sys
import os

def test_basic_functionality():
    """Run basic tests."""
    print("="*70)
    print("TESTING WIKIPEDIA DISPUTE COLLECTION TOOLKIT")
    print("="*70)
    
    # Test 1: Check if scripts are executable
    print("\n[TEST 1] Checking script files...")
    scripts = [
        'fetch_all_arbitration.py',
        'fetch_all_rfc.py',
        'analyze_arb_rfc_mapping.py',
        'run_dispute_collection.py'
    ]
    
    for script in scripts:
        if os.path.exists(script):
            print(f"  ✓ {script} found")
        else:
            print(f"  ✗ {script} NOT FOUND")
            return False
    
    # Test 2: Check imports
    print("\n[TEST 2] Checking dependencies...")
    try:
        import requests
        print("  ✓ requests module available")
    except ImportError:
        print("  ✗ requests module not found")
        print("    Run: pip install requests --break-system-packages")
        return False
    
    # Test 3: Run small collection
    print("\n[TEST 3] Running test collection (5 items)...")
    print("  This may take 30-60 seconds...")
    
    try:
        result = subprocess.run(
            [sys.executable, 'run_dispute_collection.py', 
             '--arb', '--limit', '5',
             '--output-dir', 'test_output'],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("  ✓ Test collection successful")
            print("\n[TEST 3 OUTPUT]")
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        else:
            print("  ✗ Test collection failed")
            print("\n[ERROR OUTPUT]")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("  ✗ Test timed out")
        return False
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False
    
    # Test 4: Check output
    print("\n[TEST 4] Checking output files...")
    output_file = 'test_output/arbitration_cases_full.json'
    if os.path.exists(output_file):
        size = os.path.getsize(output_file)
        print(f"  ✓ Output file created ({size} bytes)")
        
        # Try to read it
        try:
            import json
            with open(output_file, 'r') as f:
                data = json.load(f)
            print(f"  ✓ Valid JSON with {data.get('total_cases', 0)} cases")
        except Exception as e:
            print(f"  ✗ Could not parse JSON: {e}")
            return False
    else:
        print(f"  ✗ Output file not created")
        return False
    
    return True

def main():
    success = test_basic_functionality()
    
    print("\n" + "="*70)
    if success:
        print("✓ ALL TESTS PASSED")
        print("="*70)
        print("\nYou can now run:")
        print("  python run_dispute_collection.py --all")
        print("\nTo collect all arbitration cases and RfCs.")
        return 0
    else:
        print("✗ TESTS FAILED")
        print("="*70)
        print("\nPlease check the errors above and fix them.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
