#!/usr/bin/env python3
"""
Fetch all arbitration cases from Wikipedia arbitration categories.

This script collects all arbitration cases listed in the Wikipedia arbitration
categories, handling pagination and extracting case metadata.

Usage:
    python fetch_all_arbitration.py [--limit LIMIT] [--output OUTPUT]
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import unquote

try:
    import requests
except ImportError:
    print("Installing required packages...")
    os.system("pip install requests --break-system-packages")
    import requests


class WikipediaAPI:
    """Wikipedia API client with authentication support."""
    
    def __init__(self, user_agent: str = None):
        self.session = requests.Session()
        self.base_url = "https://en.wikipedia.org/w/api.php"
        
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
        
        print(f"Fetching category: {category}")
        
        while True:
            params = {
                'action': 'query',
                'list': 'categorymembers',
                'cmtitle': f'Category:{category}',
                'cmlimit': 'max',  # Get maximum per request
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
                    print(f"  Fetched {len(batch)} items (total: {len(members)})")
                    
                    if limit and len(members) >= limit:
                        members = members[:limit]
                        break
                
                # Check for continuation
                if 'continue' in data and 'cmcontinue' in data['continue']:
                    continue_token = data['continue']['cmcontinue']
                    time.sleep(0.1)  # Rate limiting
                else:
                    break
                    
            except Exception as e:
                print(f"Error fetching category members: {e}")
                break
        
        print(f"Total fetched: {len(members)} items")
        return members
    
    def get_page_content(self, page_title: str) -> Dict:
        """
        Fetch full content and metadata for a page.
        
        Args:
            page_title: Title of the Wikipedia page
        
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
            print(f"Error fetching page {page_title}: {e}")
            return None


def extract_arbitration_metadata(content: str, title: str) -> Dict:
    """
    Extract metadata from arbitration case content.
    
    Args:
        content: Wikitext content of the arbitration case
        title: Page title
    
    Returns:
        Dictionary with extracted metadata
    """
    metadata = {
        'case_name': title.replace('Wikipedia:Arbitration/Requests/Case/', '')
                          .replace('Wikipedia:Requests for arbitration/', ''),
        'status': None,
        'opened': None,
        'closed': None,
        'parties': [],
        'arbitrators': [],
        'prior_dispute_resolution': []
    }
    
    if not content:
        return metadata
    
    # Extract status
    status_patterns = [
        r'\|\s*status\s*=\s*([^\n\|]+)',
        r'\{\{status\|([^\}]+)\}\}',
        r'Case\s+status:\s*([^\n]+)'
    ]
    for pattern in status_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            metadata['status'] = match.group(1).strip()
            break
    
    # Extract dates
    date_patterns = [
        (r'opened\s*=\s*([^\n\|]+)', 'opened'),
        (r'closed\s*=\s*([^\n\|]+)', 'closed'),
        (r'date\s+opened:\s*([^\n]+)', 'opened'),
        (r'date\s+closed:\s*([^\n]+)', 'closed')
    ]
    for pattern, field in date_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            metadata[field] = match.group(1).strip()
    
    # Extract parties
    parties_section = re.search(
        r'==\s*Parties\s*==\s*(.+?)(?:==|$)',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if parties_section:
        # Find user links
        users = re.findall(r'\[\[User:([^\]|]+)', parties_section.group(1))
        metadata['parties'] = list(set(users))
    
    # Extract prior dispute resolution mentions
    pdr_section = re.search(
        r'(?:prior\s+dispute\s+resolution|evidence\s+of\s+trying|other\s+steps)(.{0,2000})',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if pdr_section:
        # Find various dispute resolution links
        drn_links = re.findall(r'\[\[Wikipedia:Dispute resolution noticeboard[^\]]*\]\]', pdr_section.group(1))
        rfc_links = re.findall(r'\[\[(?:Wikipedia:)?Requests for comment[^\]]*\]\]', pdr_section.group(1))
        anew_links = re.findall(r'\[\[Wikipedia:Administrators\' noticeboard[^\]]*\]\]', pdr_section.group(1))
        
        metadata['prior_dispute_resolution'] = {
            'drn': drn_links,
            'rfc': rfc_links,
            'an': anew_links
        }
    
    return metadata


def fetch_all_arbitration_cases(api: WikipediaAPI, limit: Optional[int] = None) -> Dict:
    """
    Fetch all arbitration cases from Wikipedia.
    
    Args:
        api: WikipediaAPI instance
        limit: Maximum number of cases to fetch
    
    Returns:
        Dictionary containing all arbitration cases
    """
    # Fetch category members
    members = api.get_category_members('Wikipedia arbitration cases', limit=limit)
    
    cases = []
    for i, member in enumerate(members, 1):
        print(f"\nFetching case {i}/{len(members)}: {member['title']}")
        
        # Get full page content
        page_data = api.get_page_content(member['title'])
        
        if page_data:
            # Extract metadata
            metadata = extract_arbitration_metadata(page_data['content'], page_data['title'])
            
            # Combine data
            case = {
                **page_data,
                'metadata': metadata,
                'fetched_at': datetime.utcnow().isoformat()
            }
            
            cases.append(case)
            
            # Rate limiting
            time.sleep(0.2)
    
    return {
        'total_cases': len(cases),
        'fetched_at': datetime.utcnow().isoformat(),
        'cases': cases
    }


def main():
    parser = argparse.ArgumentParser(
        description='Fetch all Wikipedia arbitration cases'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of cases to fetch (default: all)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='arbitration_cases_full.json',
        help='Output JSON file (default: arbitration_cases_full.json)'
    )
    
    args = parser.parse_args()
    
    # Initialize API
    api = WikipediaAPI()
    
    # Fetch all cases
    print("=" * 60)
    print("FETCHING ALL ARBITRATION CASES")
    print("=" * 60)
    
    result = fetch_all_arbitration_cases(api, limit=args.limit)
    
    # Save to file
    output_path = args.output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"COMPLETE: {result['total_cases']} cases saved to {output_path}")
    print("=" * 60)


if __name__ == '__main__':
    main()
