#!/usr/bin/env python3
"""
Map arbitration cases to requests for comment and analyze dispute resolution patterns.

This script:
1. Links arbitration cases that reference RfCs
2. Analyzes prior dispute resolution mentioned in arbitration cases
3. Categorizes and counts different types of dispute resolution

Usage:
    python analyze_arb_rfc_mapping.py [--arb FILE] [--rfc FILE] [--output FILE]
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Set, Tuple


def load_json(filepath: str) -> Dict:
    """Load JSON data from file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file: {filepath}")
        return None


def extract_rfc_references(content: str) -> List[str]:
    """
    Extract all RfC references from arbitration case content.
    
    Args:
        content: Wikitext content
    
    Returns:
        List of RfC page titles
    """
    if not content:
        return []
    
    rfc_refs = []
    
    # Pattern variations for RfC links
    patterns = [
        r'\[\[(?:meta:)?Requests for comment/([^\]|]+)',
        r'\[\[(?:m:)?RFC/([^\]|]+)',
        r'meta\.wikimedia\.org/wiki/Requests_for_comment/([^\s\]|]+)',
        r'Request for comment[:\s]+\[\[([^\]]+)\]\]',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        rfc_refs.extend(matches)
    
    # Clean up references
    cleaned = []
    for ref in rfc_refs:
        # Remove anchors and clean
        ref = ref.split('#')[0].strip()
        ref = ref.replace('_', ' ')
        if ref:
            cleaned.append(ref)
    
    return list(set(cleaned))


def extract_dispute_resolution_types(content: str) -> Dict[str, List[str]]:
    """
    Extract all types of prior dispute resolution mentioned in content.
    
    Args:
        content: Wikitext content
    
    Returns:
        Dictionary mapping dispute resolution type to list of references
    """
    if not content:
        return {}
    
    dr_types = defaultdict(list)
    
    # Define patterns for different dispute resolution venues
    dr_patterns = {
        'drn': [
            r'\[\[Wikipedia:Dispute resolution noticeboard(?:\|[^\]]+)?\]\]',
            r'\[\[WP:DRN(?:\|[^\]]+)?\]\]',
        ],
        'rfc': [
            r'\[\[(?:meta:)?Requests for comment[^\]]*\]\]',
            r'\[\[(?:Wikipedia:)?(?:RFC|RfC)[^\]]*\]\]',
        ],
        'an': [
            r'\[\[Wikipedia:Administrators\' noticeboard[^\]]*\]\]',
            r'\[\[WP:AN(?:/[^\]]+)?\]\]',
        ],
        'ani': [
            r'\[\[Wikipedia:Administrators\' noticeboard/Incidents[^\]]*\]\]',
            r'\[\[WP:ANI[^\]]*\]\]',
        ],
        'anew': [
            r'\[\[Wikipedia:Administrators\' noticeboard/Edit warring[^\]]*\]\]',
            r'\[\[WP:AN/EW[^\]]*\]\]',
            r'\[\[WP:ANEW[^\]]*\]\]',
        ],
        'mediation': [
            r'\[\[Wikipedia:Mediation[^\]]*\]\]',
            r'\[\[WP:MEDCAB[^\]]*\]\]',
            r'\[\[Wikipedia:Mediation Committee[^\]]*\]\]',
        ],
        'third_opinion': [
            r'\[\[Wikipedia:Third opinion[^\]]*\]\]',
            r'\[\[WP:3O[^\]]*\]\]',
        ],
        'talk_page': [
            r'[Tt]alk[ -]page discussion',
            r'article talk page',
            r'user talk page',
        ],
        'other': []
    }
    
    for dr_type, patterns in dr_patterns.items():
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                dr_types[dr_type].extend(matches)
    
    # Convert to regular dict and deduplicate
    result = {}
    for dr_type, refs in dr_types.items():
        if refs:
            result[dr_type] = list(set(refs))
    
    return result


def analyze_case_content(case: Dict) -> Dict:
    """
    Analyze a single arbitration case for dispute resolution references.
    
    Args:
        case: Arbitration case dictionary
    
    Returns:
        Analysis results
    """
    content = case.get('content', '')
    
    return {
        'case_title': case.get('title'),
        'case_name': case.get('metadata', {}).get('case_name'),
        'rfc_references': extract_rfc_references(content),
        'dispute_resolution_types': extract_dispute_resolution_types(content),
        'has_prior_dr': bool(extract_dispute_resolution_types(content)),
    }


def map_arb_to_rfc(arb_data: Dict, rfc_data: Dict) -> Dict:
    """
    Map arbitration cases to RfCs and analyze dispute resolution patterns.
    
    Args:
        arb_data: Arbitration cases data
        rfc_data: RfC data
    
    Returns:
        Mapping and analysis results
    """
    print("\nAnalyzing arbitration cases...")
    
    # Build RfC lookup
    rfc_lookup = {}
    if rfc_data and 'rfcs_by_status' in rfc_data:
        for status, rfcs in rfc_data['rfcs_by_status'].items():
            for rfc in rfcs:
                title = rfc.get('title', '')
                # Normalize title
                normalized = title.replace('Requests for comment/', '').strip()
                rfc_lookup[normalized.lower()] = {
                    'title': title,
                    'status': status,
                    'url': rfc.get('url')
                }
    
    # Analyze each arbitration case
    case_analyses = []
    dr_type_counter = Counter()
    rfc_references_counter = Counter()
    
    cases = arb_data.get('cases', [])
    for i, case in enumerate(cases, 1):
        if i % 50 == 0:
            print(f"  Analyzed {i}/{len(cases)} cases...")
        
        analysis = analyze_case_content(case)
        
        # Count dispute resolution types
        for dr_type in analysis['dispute_resolution_types'].keys():
            dr_type_counter[dr_type] += 1
        
        # Try to match RfC references
        matched_rfcs = []
        for rfc_ref in analysis['rfc_references']:
            normalized_ref = rfc_ref.lower()
            if normalized_ref in rfc_lookup:
                matched_rfcs.append(rfc_lookup[normalized_ref])
                rfc_references_counter[rfc_ref] += 1
        
        analysis['matched_rfcs'] = matched_rfcs
        case_analyses.append(analysis)
    
    print(f"  Completed analysis of {len(cases)} cases")
    
    # Compile statistics
    cases_with_rfc = sum(1 for a in case_analyses if a['rfc_references'])
    cases_with_matched_rfc = sum(1 for a in case_analyses if a['matched_rfcs'])
    cases_with_prior_dr = sum(1 for a in case_analyses if a['has_prior_dr'])
    
    statistics = {
        'total_cases_analyzed': len(cases),
        'cases_with_rfc_reference': cases_with_rfc,
        'cases_with_matched_rfc': cases_with_matched_rfc,
        'cases_with_prior_dispute_resolution': cases_with_prior_dr,
        'dispute_resolution_type_counts': dict(dr_type_counter),
        'most_referenced_rfcs': dict(rfc_references_counter.most_common(20))
    }
    
    # Create summary
    summary = {
        'analysis_timestamp': datetime.utcnow().isoformat(),
        'statistics': statistics,
        'case_analyses': case_analyses,
        'dispute_resolution_types_found': list(dr_type_counter.keys())
    }
    
    return summary


def generate_report(analysis: Dict) -> str:
    """
    Generate a human-readable report from analysis.
    
    Args:
        analysis: Analysis results
    
    Returns:
        Formatted report string
    """
    stats = analysis['statistics']
    
    report = []
    report.append("=" * 70)
    report.append("ARBITRATION CASE TO RFC MAPPING ANALYSIS")
    report.append("=" * 70)
    report.append("")
    
    report.append("OVERVIEW:")
    report.append(f"  Total cases analyzed: {stats['total_cases_analyzed']}")
    report.append(f"  Cases referencing RfCs: {stats['cases_with_rfc_reference']} "
                  f"({stats['cases_with_rfc_reference']/stats['total_cases_analyzed']*100:.1f}%)")
    report.append(f"  Cases with matched RfCs: {stats['cases_with_matched_rfc']} "
                  f"({stats['cases_with_matched_rfc']/stats['total_cases_analyzed']*100:.1f}%)")
    report.append(f"  Cases with prior DR: {stats['cases_with_prior_dispute_resolution']} "
                  f"({stats['cases_with_prior_dispute_resolution']/stats['total_cases_analyzed']*100:.1f}%)")
    report.append("")
    
    report.append("DISPUTE RESOLUTION TYPES FOUND:")
    dr_counts = stats['dispute_resolution_type_counts']
    for dr_type, count in sorted(dr_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = count / stats['total_cases_analyzed'] * 100
        report.append(f"  {dr_type.upper()}: {count} cases ({percentage:.1f}%)")
    report.append("")
    
    if stats['most_referenced_rfcs']:
        report.append("MOST REFERENCED RFCs:")
        for rfc, count in list(stats['most_referenced_rfcs'].items())[:10]:
            report.append(f"  {rfc}: {count} references")
        report.append("")
    
    report.append("=" * 70)
    
    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(
        description='Map arbitration cases to RfCs and analyze dispute resolution'
    )
    parser.add_argument(
        '--arb',
        type=str,
        default='arbitration_cases_full.json',
        help='Arbitration cases JSON file'
    )
    parser.add_argument(
        '--rfc',
        type=str,
        default='requests_for_comment_full.json',
        help='RfCs JSON file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='arb_rfc_mapping.json',
        help='Output JSON file'
    )
    parser.add_argument(
        '--report',
        type=str,
        default='arb_rfc_report.txt',
        help='Output report file'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("ARBITRATION CASE TO RFC MAPPING ANALYSIS")
    print("=" * 70)
    
    # Load data
    print("\nLoading data files...")
    arb_data = load_json(args.arb)
    rfc_data = load_json(args.rfc)
    
    if not arb_data:
        print("Error: Could not load arbitration data")
        return
    
    if not rfc_data:
        print("Warning: Could not load RfC data, continuing with limited analysis")
    
    # Perform mapping and analysis
    analysis = map_arb_to_rfc(arb_data, rfc_data)
    
    # Save results
    print(f"\nSaving analysis to {args.output}...")
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    # Generate and save report
    print(f"Generating report to {args.report}...")
    report = generate_report(analysis)
    with open(args.report, 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Print report to console
    print("\n" + report)
    
    print(f"\nAnalysis complete!")
    print(f"  JSON output: {args.output}")
    print(f"  Report: {args.report}")


if __name__ == '__main__':
    main()
