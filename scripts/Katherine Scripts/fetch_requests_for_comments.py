#!/usr/bin/env python3
"""
Fetch all Requests for Comments from Meta-Wiki.

This script retrieves all RfCs from multiple categories on Meta-Wiki:
- Resolved
- Unsuccessful  
- Invalid
- Inactive
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from wiki import WikiClient
from io import save_json, get_output_path
import time


def fetch_rfc_category(client: WikiClient, category: str) -> list:
    """
    Fetch RfCs from a specific category.
    
    Args:
        client: WikiClient instance
        category: Category name (without "Category:" prefix)
    
    Returns:
        List of RfC pages with content
    """
    print(f"\nFetching from category: {category}")
    
    # Get all members of the category
    members = client.get_category_members(
        category,
        api_url=client.meta_wiki_api,
        limit=500
    )
    
    print(f"  Found {len(members)} items")
    
    # Filter to only include pages
    pages = [m for m in members if m.get('type') == 'page']
    
    print(f"  Found {len(pages)} RfC pages")
    
    # Fetch full content for each RfC
    detailed_rfcs = []
    
    for i, page in enumerate(pages, 1):
        if i % 50 == 0:
            print(f"    Fetching {i}/{len(pages)}...")
        
        try:
            # Get page content
            page_data = client.get_page_content(page['title'], api_url=client.meta_wiki_api)
            
            # Extract content from response
            if 'query' in page_data and 'pages' in page_data['query']:
                page_obj = page_data['query']['pages'][0]
                
                if 'revisions' in page_obj and len(page_obj['revisions']) > 0:
                    revision = page_obj['revisions'][0]
                    content = revision.get('slots', {}).get('main', {}).get('content', '')
                    
                    rfc_info = {
                        'title': page['title'],
                        'page_id': page_obj.get('pageid'),
                        'timestamp': page.get('timestamp'),
                        'category': category,
                        'content': content,
                        'last_revision_user': revision.get('user'),
                        'last_revision_comment': revision.get('comment'),
                        'last_revision_timestamp': revision.get('timestamp')
                    }
                    
                    detailed_rfcs.append(rfc_info)
            
            # Rate limiting
            if i % 10 == 0:
                time.sleep(0.5)
                
        except Exception as e:
            print(f"    Error fetching {page['title']}: {e}")
            continue
    
    return detailed_rfcs


def fetch_all_rfcs(client: WikiClient) -> dict:
    """
    Fetch all RfCs from all categories.
    
    Args:
        client: WikiClient instance
    
    Returns:
        Dictionary containing all RfCs organized by category
    """
    categories = [
        'Requests for comments (resolved)',
        'Requests for comments (unsuccessful)',
        'Requests for comments (invalid)',
        'Requests for comments (inactive)'
    ]
    
    all_rfcs = []
    category_counts = {}
    
    for category in categories:
        rfcs = fetch_rfc_category(client, category)
        category_counts[category] = len(rfcs)
        all_rfcs.extend(rfcs)
    
    return {
        'source': 'Meta-Wiki Requests for Comments',
        'fetch_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'categories_fetched': categories,
        'category_counts': category_counts,
        'total_rfcs': len(all_rfcs),
        'rfcs': all_rfcs
    }


def main():
    """Main execution function."""
    print("=" * 60)
    print("Meta-Wiki Requests for Comments Fetcher")
    print("=" * 60)
    
    # Initialize client
    client = WikiClient()
    
    # Fetch all RfCs
    data = fetch_all_rfcs(client)
    
    # Save to file
    output_path = get_output_path('rfc', prefix='all_requests_for_comments')
    save_json(data, output_path)
    
    print("\n" + "=" * 60)
    print("SUCCESS: Saved RfCs to file")
    print(f"  Total RfCs: {data['total_rfcs']}")
    print(f"  By category:")
    for cat, count in data['category_counts'].items():
        print(f"    {cat}: {count}")
    print(f"\n  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
