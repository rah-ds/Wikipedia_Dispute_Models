#!/usr/bin/env python3
"""
Fetch all Requests for Comment (RfC) from Meta-Wiki.

This script collects RfCs from multiple status categories on Meta-Wiki.

Usage:
    python fetch_all_rfc.py [--limit LIMIT] [--output OUTPUT]
"""

import argparse
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Optional

try:
    import requests
except ImportError:
    print("Installing required packages...")
    os.system("pip install requests --break-system-packages")
    import requests


class MetaWikiAPI:
    """Meta-Wiki API client with authentication support."""
    
    def __init__(self, user_agent: str = None):
        self.session = requests.Session()
        self.base_url = "https://meta.wikimedia.org/w/api.php"
        
        # Load credentials from environment
        self.access_token = os.getenv('WIKIPEDIA_ACCESS_TOKEN')
        
        if user_agent:
            self.session.headers['User-Agent'] = user_agent
        else:
            self.session.headers['User-Agent'] = 'WikiDisputeCollector/1.0 (Research Project)'
        
        # Set authorization header if token is available
        if self.access_token:
            self.session.headers['Authorization'] = f'Bearer {self.access_token}'
    
    def get_category_members(self, category: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch all members of a category, handling pagination.
        
        Args:
            category: Category name (without 'Category:' prefix)
            limit: Maximum number of pages to fetch (None for all)
        
        Returns:
            List of category members with metadata
        """
        members = []
        continue_token = None
        
        print(f"  Fetching category: {category}")
        
        while True:
            params = {
                'action': 'query',
                'list': 'categorymembers',
                'cmtitle': f'Category:{category}',
                'cmlimit': 'max',
                'format': 'json',
                'cmprop': 'title|timestamp|ids'
            }
            
            if continue_token:
                params['cmcontinue'] = continue_token
            
            try:
                response = self.session.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if 'query' in data and 'categorymembers' in data['query']:
                    batch = data['query']['categorymembers']
                    members.extend(batch)
                    print(f"    Fetched {len(batch)} items (total: {len(members)})")
                    
                    if limit and len(members) >= limit:
                        members = members[:limit]
                        break
                
                # Check for continuation
                if 'continue' in data and 'cmcontinue' in data['continue']:
                    continue_token = data['continue']['cmcontinue']
                    time.sleep(0.1)
                else:
                    break
                    
            except Exception as e:
                print(f"    Error fetching category members: {e}")
                break
        
        print(f"    Total: {len(members)} items")
        return members
    
    def get_page_content(self, page_title: str) -> Dict:
        """
        Fetch full content and metadata for a page.
        
        Args:
            page_title: Title of the page
        
        Returns:
            Dictionary with page content and metadata
        """
        params = {
            'action': 'query',
            'titles': page_title,
            'prop': 'revisions|categories|info',
            'rvprop': 'content|timestamp|user|comment|ids',
            'rvslots': 'main',
            'inprop': 'url',
            'format': 'json'
        }
        
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            pages = data['query']['pages']
            page_id = list(pages.keys())[0]
            page = pages[page_id]
            
            result = {
                'pageid': page.get('pageid'),
                'title': page.get('title'),
                'url': page.get('fullurl'),
                'categories': [cat['title'] for cat in page.get('categories', [])],
                'content': None,
                'timestamp': None,
                'user': None,
                'comment': None
            }
            
            if 'revisions' in page and len(page['revisions']) > 0:
                rev = page['revisions'][0]
                if 'slots' in rev and 'main' in rev['slots']:
                    result['content'] = rev['slots']['main'].get('*', '')
                result['timestamp'] = rev.get('timestamp')
                result['user'] = rev.get('user')
                result['comment'] = rev.get('comment')
            
            return result
            
        except Exception as e:
            print(f"    Error fetching page {page_title}: {e}")
            return None


def fetch_all_rfcs(api: MetaWikiAPI, limit: Optional[int] = None) -> Dict:
    """
    Fetch all RfCs from Meta-Wiki across all status categories.
    
    Args:
        api: MetaWikiAPI instance
        limit: Maximum number of RfCs to fetch per category
    
    Returns:
        Dictionary containing all RfCs organized by status
    """
    # Define RfC categories
    rfc_categories = {
        'resolved': 'Requests for comments (resolved)',
        'unsuccessful': 'Requests for comments (unsuccessful)',
        'invalid': 'Requests for comments (invalid)',
        'inactive': 'Requests for comments (inactive)',
        'active': 'Requests for comments (active)'  # May or may not exist
    }
    
    all_rfcs = {}
    total_count = 0
    
    for status, category in rfc_categories.items():
        print(f"\nFetching {status.upper()} RfCs:")
        
        try:
            # Fetch category members
            members = api.get_category_members(category, limit=limit)
            
            rfcs = []
            for i, member in enumerate(members, 1):
                print(f"  Fetching RfC {i}/{len(members)}: {member['title'][:60]}...")
                
                # Get full page content
                page_data = api.get_page_content(member['title'])
                
                if page_data:
                    rfc = {
                        **page_data,
                        'status': status,
                        'fetched_at': datetime.utcnow().isoformat()
                    }
                    rfcs.append(rfc)
                    
                    # Rate limiting
                    time.sleep(0.2)
            
            all_rfcs[status] = rfcs
            total_count += len(rfcs)
            print(f"  Collected {len(rfcs)} {status} RfCs")
            
        except Exception as e:
            print(f"  Error fetching {status} RfCs: {e}")
            all_rfcs[status] = []
    
    return {
        'total_rfcs': total_count,
        'fetched_at': datetime.utcnow().isoformat(),
        'rfcs_by_status': all_rfcs
    }


def main():
    parser = argparse.ArgumentParser(
        description='Fetch all Meta-Wiki Requests for Comment'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of RfCs per category (default: all)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='requests_for_comment_full.json',
        help='Output JSON file (default: requests_for_comment_full.json)'
    )
    
    args = parser.parse_args()
    
    # Initialize API
    api = MetaWikiAPI()
    
    # Fetch all RfCs
    print("=" * 60)
    print("FETCHING ALL REQUESTS FOR COMMENT (Meta-Wiki)")
    print("=" * 60)
    
    result = fetch_all_rfcs(api, limit=args.limit)
    
    # Save to file
    output_path = args.output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"COMPLETE: {result['total_rfcs']} RfCs saved to {output_path}")
    print("=" * 60)


if __name__ == '__main__':
    main()
