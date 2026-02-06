#!/usr/bin/env python3
"""
Analyze relationships between arbitration cases and requests for comments.

This script:
1. Maps arbitration cases to RfCs they reference
2. Extracts and categorizes prior dispute resolution methods mentioned
"""

import sys
from pathlib import Path
import re
from collections import defaultdict, Counter

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from io import save_json, load_json, get_output_path
import time


def find_rfc_references(content: str) -> list:
    """
    Find references to Requests for Comments in arbitration case content.
    
    Args:
        content: Page content to search
    
    Returns:
        List of RfC references found
    """
    rfc_refs = []
    
    # Pattern 1: Direct links to RfC pages
    pattern1 = r'\[\[(?:meta:|m:)?Requests for comment/([^\]|]+)'
    matches1 = re.findall(pattern1, content, re.IGNORECASE)
    rfc_refs.extend(['Requests for comment/' + m for m in matches1])
    
    # Pattern 2: RfC mentions in text
    pattern2 = r'Request(?:s)? for (?:C|c)omment(?:s)?[:\s]+([^\n\]]+?)(?:\||]|\n)'
    matches2 = re.findall(pattern2, content, re.IGNORECASE)
    rfc_refs.extend(matches2)
    
    # Pattern 3: Meta-wiki RfC links
    pattern3 = r'meta\.wikimedia\.org/wiki/Requests_for_comment/([^"\s\]]+)'
    matches3 = re.findall(pattern3, content, re.IGNORECASE)
    rfc_refs.extend(['Requests for comment/' + m for m in matches3])
    
    return list(set(rfc_refs))  # Remove duplicates


def extract_dispute_resolution_methods(content: str) -> dict:
    """
    Extract and categorize dispute resolution methods mentioned in content.
    
    Args:
        content: Page content to analyze
    
    Returns:
        Dictionary with categorized dispute resolution methods
    """
    methods = {
        'formal_methods': [],
        'informal_methods': [],
        'venue_types': Counter(),
        'all_mentions': []
    }
    
    # Common dispute resolution venues and methods
    formal_venues = [
        r'Arbitration Enforcement',
        r'Arbitration Committee',
        r'ArbCom',
        r'Request(?:s)? for (?:C|c)omment',
        r'RfC',
        r'Dispute [Rr]esolution [Nn]oticeboard',
        r'DRN',
        r'Administrator(?:s)?\' [Nn]oticeboard',
        r'AN/I',
        r'ANI',
        r'3RR',
        r'Edit [Ww]ar',
        r'Mediation',
        r'MedCom',
        r'Admin [Nn]oticeboard'
    ]
    
    informal_methods = [
        r'[Tt]alk page discussion',
        r'[Uu]ser talk',
        r'[Aa]rticle talk',
        r'[Tt]hird [Oo]pinion',
        r'3O',
        r'[Ii]nformal [Mm]ediation',
        r'[Cc]ontent [Dd]ispute',
        r'[Ee]dit [Dd]iscussion'
    ]
    
    # Search for formal venues
    for pattern in formal_venues:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            methods['formal_methods'].extend(matches)
            methods['venue_types'][pattern] += len(matches)
            methods['all_mentions'].extend(matches)
    
    # Search for informal methods
    for pattern in informal_methods:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            methods['informal_methods'].extend(matches)
            methods['venue_types'][pattern] += len(matches)
            methods['all_mentions'].extend(matches)
    
    # Look for "prior dispute resolution" or "proof of prior dispute resolution" sections
    prior_dr_pattern = r'(?:Prior|Proof of prior) dispute resolution[:\s]+([^\n]+(?:\n(?![=\n])[^\n]+)*)'
    prior_dr_matches = re.findall(prior_dr_pattern, content, re.IGNORECASE | re.MULTILINE)
    
    if prior_dr_matches:
        methods['prior_dr_sections'] = prior_dr_matches
    
    # Convert Counter to dict for JSON serialization
    methods['venue_types'] = dict(methods['venue_types'])
    
    return methods


def analyze_case_rfc_relationships(arb_data: dict, rfc_data: dict) -> dict:
    """
    Analyze relationships between arbitration cases and RfCs.
    
    Args:
        arb_data: Arbitration cases data
        rfc_data: Requests for comments data
    
    Returns:
        Analysis results
    """
    print("\nAnalyzing arbitration case → RfC relationships...")
    
    # Create RfC title lookup
    rfc_titles = {rfc['title'].lower(): rfc for rfc in rfc_data['rfcs']}
    
    relationships = []
    cases_with_rfcs = 0
    total_rfc_refs = 0
    
    for i, case in enumerate(arb_data['cases'], 1):
        if i % 50 == 0:
            print(f"  Analyzed {i}/{len(arb_data['cases'])} cases...")
        
        # Find RfC references
        rfc_refs = find_rfc_references(case['content'])
        
        # Extract dispute resolution methods
        dr_methods = extract_dispute_resolution_methods(case['content'])
        
        case_analysis = {
            'case_title': case['title'],
            'case_page_id': case['page_id'],
            'rfc_references': rfc_refs,
            'rfc_count': len(rfc_refs),
            'dispute_resolution_methods': dr_methods,
            'formal_dr_count': len(dr_methods['formal_methods']),
            'informal_dr_count': len(dr_methods['informal_methods']),
            'venue_type_summary': dr_methods['venue_types']
        }
        
        relationships.append(case_analysis)
        
        if rfc_refs:
            cases_with_rfcs += 1
            total_rfc_refs += len(rfc_refs)
    
    print(f"  Complete! Analyzed {len(arb_data['cases'])} cases")
    
    return relationships, cases_with_rfcs, total_rfc_refs


def generate_summary_statistics(relationships: list) -> dict:
    """
    Generate summary statistics from the analysis.
    
    Args:
        relationships: List of case-RfC relationships
    
    Returns:
        Summary statistics
    """
    stats = {
        'total_cases_analyzed': len(relationships),
        'cases_with_rfc_refs': sum(1 for r in relationships if r['rfc_count'] > 0),
        'total_rfc_references': sum(r['rfc_count'] for r in relationships),
        'cases_with_formal_dr': sum(1 for r in relationships if r['formal_dr_count'] > 0),
        'cases_with_informal_dr': sum(1 for r in relationships if r['informal_dr_count'] > 0),
        'venue_type_totals': Counter()
    }
    
    # Aggregate venue types
    for rel in relationships:
        for venue, count in rel['venue_type_summary'].items():
            stats['venue_type_totals'][venue] += count
    
    stats['venue_type_totals'] = dict(stats['venue_type_totals'].most_common())
    
    # Top cases by RfC references
    stats['top_cases_by_rfc_refs'] = sorted(
        [(r['case_title'], r['rfc_count']) for r in relationships if r['rfc_count'] > 0],
        key=lambda x: x[1],
        reverse=True
    )[:20]
    
    # Top cases by dispute resolution mentions
    stats['top_cases_by_dr_mentions'] = sorted(
        [(r['case_title'], r['formal_dr_count'] + r['informal_dr_count']) 
         for r in relationships],
        key=lambda x: x[1],
        reverse=True
    )[:20]
    
    return stats


def main():
    """Main execution function."""
    print("=" * 60)
    print("Arbitration Case → RfC Relationship Analyzer")
    print("=" * 60)
    
    # Find the most recent data files
    data_dir = Path(__file__).parent.parent / "data" / "raw"
    
    arb_dir = data_dir / "arbitration"
    rfc_dir = data_dir / "rfc"
    
    # Check if data exists
    if not arb_dir.exists() or not rfc_dir.exists():
        print("\nERROR: Data files not found!")
        print("Please run the following scripts first:")
        print("  1. fetch_arbitration_cases.py")
        print("  2. fetch_requests_for_comments.py")
        sys.exit(1)
    
    # Get most recent files
    arb_files = sorted(arb_dir.glob("*.json"), reverse=True)
    rfc_files = sorted(rfc_dir.glob("*.json"), reverse=True)
    
    if not arb_files or not rfc_files:
        print("\nERROR: Data files not found!")
        print("Please run the fetch scripts first.")
        sys.exit(1)
    
    print(f"\nLoading arbitration data from: {arb_files[0].name}")
    arb_data = load_json(arb_files[0])
    
    print(f"Loading RfC data from: {rfc_files[0].name}")
    rfc_data = load_json(rfc_files[0])
    
    print(f"\nData loaded:")
    print(f"  Arbitration cases: {len(arb_data['cases'])}")
    print(f"  RfCs: {len(rfc_data['rfcs'])}")
    
    # Analyze relationships
    relationships, cases_with_rfcs, total_rfc_refs = analyze_case_rfc_relationships(
        arb_data, rfc_data
    )
    
    # Generate summary statistics
    print("\nGenerating summary statistics...")
    stats = generate_summary_statistics(relationships)
    
    # Prepare output
    output = {
        'analysis_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'source_files': {
            'arbitration': str(arb_files[0]),
            'rfc': str(rfc_files[0])
        },
        'summary_statistics': stats,
        'case_relationships': relationships
    }
    
    # Save results
    output_path = get_output_path('analysis', prefix='arb_rfc_relationships')
    save_json(output, output_path)
    
    # Print summary
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"\nSummary Statistics:")
    print(f"  Total cases analyzed: {stats['total_cases_analyzed']}")
    print(f"  Cases with RfC references: {stats['cases_with_rfc_refs']}")
    print(f"  Total RfC references: {stats['total_rfc_references']}")
    print(f"  Cases with formal DR: {stats['cases_with_formal_dr']}")
    print(f"  Cases with informal DR: {stats['cases_with_informal_dr']}")
    print(f"\nTop Dispute Resolution Venues:")
    for venue, count in list(stats['venue_type_totals'].items())[:10]:
        print(f"  {venue}: {count}")
    print(f"\n  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
