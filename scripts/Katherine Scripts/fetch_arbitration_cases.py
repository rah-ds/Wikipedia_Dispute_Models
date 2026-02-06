#!/usr/bin/env python3
"""
Fetch all Wikipedia arbitration cases from the category.

This script retrieves all arbitration cases listed in the
"Wikipedia arbitration cases" category on English Wikipedia.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from wiki import WikiClient
from io import save_json, get_output_path
import time
import re


def fetch_arbitration_cases(client: WikiClient) -> dict:
    """
    Fetch all arbitration cases from the Wikipedia category.
    
    Args:
        client: WikiClient instance
    
    Returns:
        Dictionary containing all arbitration cases with metadata
    """
    print("Fetching arbitration cases from category...")
    
    # Get all members of the arbitration cases category
    members = client.get_category_members(
        'Wikipedia arbitration cases',
        limit=500
    )
    
    print(f"Found {len(members)} items in category")
    
    # Filter to only include pages (not subcategories)
    cases = [m for m in members if m.get('type') == 'page']
    
    print(f"Found {len(cases)} arbitration case pages")
    
    # Fetch full content for each case
    detailed_cases = []
    
    for i, case in enumerate(cases, 1):
        print(f"Fetching case {i}/{len(cases)}: {case['title']}")
        
        try:
            # Get page content
            page_data = client.get_page_content(case['title'])
            
            # Extract content from response
            if 'query' in page_data and 'pages' in page_data['query']:
                page = page_data['query']['pages'][0]
                
                if 'revisions' in page and len(page['revisions']) > 0:
                    revision = page['revisions'][0]
                    content = revision.get('slots', {}).get('main', {}).get('content', '')
                    
                    case_info = {
                        'title': case['title'],
                        'page_id': page.get('pageid'),
                        'timestamp': case.get('timestamp'),
                        'content': content,
                        'last_revision_user': revision.get('user'),
                        'last_revision_comment': revision.get('comment'),
                        'last_revision_timestamp': revision.get('timestamp')
                    }
                    
                    detailed_cases.append(case_info)
            
            # Rate limiting to be respectful
            if i % 10 == 0:
                time.sleep(1)
                
        except Exception as e:
            print(f"Error fetching {case['title']}: {e}")
            continue
    
    return {
        'category': 'Wikipedia arbitration cases',
        'fetch_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_cases': len(detailed_cases),
        'cases': detailed_cases
    }


def main():
    """Main execution function."""
    print("=" * 60)
    print("Wikipedia Arbitration Cases Fetcher")
    print("=" * 60)
    
    # Initialize client
    client = WikiClient()
    
    # Fetch arbitration cases
    data = fetch_arbitration_cases(client)
    
    # Save to file
    output_path = get_output_path('arbitration', prefix='all_arbitration_cases')
    save_json(data, output_path)
    
    print("\n" + "=" * 60)
    print(f"SUCCESS: Saved {data['total_cases']} cases to:")
    print(f"  {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
