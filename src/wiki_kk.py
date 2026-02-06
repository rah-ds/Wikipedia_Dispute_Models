#!/usr/bin/env python3
"""
Wikipedia API client with OAuth support.
"""

import os
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class WikiClient:
    """Client for interacting with Wikipedia and Meta-Wiki APIs."""
    
    def __init__(self, use_auth: bool = True):
        """
        Initialize the Wikipedia client.
        
        Args:
            use_auth: Whether to use OAuth authentication (recommended)
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'WikipediaDisputeResearch/1.0 (Research Project; Contact: [email protected])'
        })
        
        if use_auth:
            self.access_token = os.getenv('WIKIPEDIA_ACCESS_TOKEN')
            if self.access_token:
                self.session.headers.update({
                    'Authorization': f'Bearer {self.access_token}'
                })
        
        self.en_wiki_api = "https://en.wikipedia.org/w/api.php"
        self.meta_wiki_api = "https://meta.wikimedia.org/w/api.php"
    
    def get(self, params: Dict[str, Any], api_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Make a GET request to the Wikipedia API.
        
        Args:
            params: API parameters
            api_url: API endpoint URL (defaults to English Wikipedia)
        
        Returns:
            JSON response from the API
        """
        if api_url is None:
            api_url = self.en_wiki_api
        
        # Add format=json if not specified
        if 'format' not in params:
            params['format'] = 'json'
        
        response = self.session.get(api_url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_page_content(self, title: str, api_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the full content of a Wikipedia page.
        
        Args:
            title: Page title
            api_url: API endpoint URL
        
        Returns:
            Page content and metadata
        """
        params = {
            'action': 'query',
            'prop': 'revisions',
            'titles': title,
            'rvprop': 'content|timestamp|user|comment',
            'rvslots': 'main',
            'formatversion': 2
        }
        
        return self.get(params, api_url)
    
    def get_category_members(self, category: str, api_url: Optional[str] = None, 
                            limit: int = 500) -> list:
        """
        Get all members of a category.
        
        Args:
            category: Category name (without "Category:" prefix)
            api_url: API endpoint URL
            limit: Maximum number of results per request
        
        Returns:
            List of category members
        """
        if api_url is None:
            api_url = self.en_wiki_api
        
        members = []
        cmcontinue = None
        
        while True:
            params = {
                'action': 'query',
                'list': 'categorymembers',
                'cmtitle': f'Category:{category}',
                'cmlimit': limit,
                'cmprop': 'title|timestamp|type'
            }
            
            if cmcontinue:
                params['cmcontinue'] = cmcontinue
            
            data = self.get(params, api_url)
            
            if 'query' in data and 'categorymembers' in data['query']:
                members.extend(data['query']['categorymembers'])
            
            # Check for continuation
            if 'continue' in data and 'cmcontinue' in data['continue']:
                cmcontinue = data['continue']['cmcontinue']
                print(f"Fetched {len(members)} members, continuing...")
            else:
                break
        
        return members
