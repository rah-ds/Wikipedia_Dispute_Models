import os
import re
import json
import time
import requests
import pandas as pd
import logging
from typing import List, Dict, Any, Generator, Optional
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
API_URL = "https://en.wikipedia.org/w/api.php"
EMAIL = os.getenv("WIKIPEDIA_EMAIL")
LOG_FILE = "fetch_arbitration.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if not EMAIL:
    logger.error("WIKIPEDIA_EMAIL not found in environment variables.")
    raise ValueError("Please set WIKIPEDIA_EMAIL in your .env file.")

HEADERS = {
    "User-Agent": f"WikipediaDisputeScraper ({EMAIL})"
}

# Define paths relative to the script location or project root
OUTPUT_FILE = "arbitration_pages.json" 

def get_case_titles_from_api(session: requests.Session) -> List[str]:
    """
    Fetch all arbitration case titles from Category:Wikipedia_arbitration_cases.
    
    Args:
        session (requests.Session): The requests session.
        
    Returns:
        List[str]: A list of page titles.
    """
    titles = []
    base_params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Wikipedia arbitration cases",
        "cmlimit": "max",
        "format": "json",
    }
    
    params = base_params.copy()
    
    logger.info("Fetching case titles from Category:Wikipedia_arbitration_cases...")
    
    while True:
        data = fetch_with_retry(session, params)
        if not data:
            break
            
        members = data.get("query", {}).get("categorymembers", [])
        for member in members:
            titles.append(member["title"])
            
        if "continue" in data:
            params.update(data["continue"])
        else:
            break
            
    logger.info(f"Found {len(titles)} cases from API.")
    return titles

def chunk_list(lst: List[Any], n: int = 50) -> Generator[List[Any], None, None]:
    """
    Yield successive n-sized chunks from a list.

    Args:
        lst (List[Any]): The list to be chunked.
        n (int, optional): The size of each chunk. Defaults to 50.

    Yields:
        Generator[List[Any], None, None]: A generator yielding chunks of the list.
    """
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def fetch_with_retry(session: requests.Session, params: Dict[str, str], max_retries: int = 5) -> Optional[Dict[str, Any]]:
    """
    Fetch data from API with retry logic for rate limits (429) and other errors.
    Only sleeps when a rate limit or error is encountered.

    Args:
        session (requests.Session): The requests session to use for making requests.
        params (Dict[str, str]): The parameters to send with the request.
        max_retries (int, optional): The maximum number of retry attempts. Defaults to 5.

    Returns:
        Optional[Dict[str, Any]]: The JSON response from the API, or None if the request failed after retries.
    """
    for attempt in range(max_retries):
        try:
            resp = session.get(API_URL, headers=HEADERS, params=params)
            
            if resp.status_code == 200:
                return resp.json()
            
            if resp.status_code == 429:
                # Rate limit hit
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning(f"Rate limit hit (429). Sleeping for {retry_after}s. Attempt {attempt + 1}/{max_retries}")
                time.sleep(retry_after)
                continue
            
            # Other HTTP errors
            logger.error(f"HTTP error {resp.status_code}. Attempt {attempt + 1}/{max_retries}")
            time.sleep(1) # Short backoff for other errors
            
        except requests.RequestException as e:
            logger.error(f"Request exception: {e}. Attempt {attempt + 1}/{max_retries}")
            time.sleep(1)
            
    logger.error("Max retries exceeded.")
    return None

def main() -> None:
    """
    Main function to execute the script logic:
    1. Fetch case titles from API.
    2. Load existing extracted data if available.
    3. Fetch new pages from Wikipedia API in chunks.
    """
    with requests.Session() as session:
        # 1. Fetch Titles
        titles_to_fetch_raw = get_case_titles_from_api(session)
        
        if not titles_to_fetch_raw:
            logger.warning("No titles found. Exiting.")
            return

        # Prepare list
        titles_to_fetch = [t.replace(' ', '_') for t in titles_to_fetch_raw]
        
        # 2. Load Existing Data
        all_pages_data = []
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                    all_pages_data = json.load(f)
                logger.info(f"Loaded {len(all_pages_data)} existing pages from {OUTPUT_FILE}")
            except (FileNotFoundError, json.JSONDecodeError):
                logger.warning(f"Could not read existing {OUTPUT_FILE}, starting fresh.")
                all_pages_data = []
        else:
            logger.info(f"Creating new output file: {OUTPUT_FILE}")

        # Optimize duplication check
        existing_titles = {d.get("title") for d in all_pages_data}
        
        # Convert API titles to readable format to match typical API response "title" field
        # (Though "title" in response usually has spaces)
        unique_titles = list(set(titles_to_fetch_raw))
        final_titles_to_query = [t for t in unique_titles if t not in existing_titles]
        
        logger.info(f"Total titles found: {len(unique_titles)}. Already have: {len(existing_titles)}. To fetch: {len(final_titles_to_query)}")

        if not final_titles_to_query:
            logger.info("All pages already fetched.")
            return

        # 3. Fetch Data
        chunks = list(chunk_list(final_titles_to_query, 50))
        logger.info(f"Fetching {len(final_titles_to_query)} pages in {len(chunks)} chunks...")
        
        for chunk in tqdm(chunks, desc="Fetching pages"):
            params = {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(chunk),
                "format": "json",
                "formatversion": "2",
                "redirects": "1"
            }

            data = fetch_with_retry(session, params)
            
            if not data:
                logger.error(f"Failed to fetch chunk starting with {chunk[0]}. Skipping.")
                continue

            pages = data.get("query", {}).get("pages", [])
            new_items_count = 0
            
            for page in pages:
                title = page.get("title", "")
                revisions = page.get("revisions", [])
                wikitext = ""
                if revisions and "slots" in revisions[0]:
                    wikitext = revisions[0]["slots"]["main"].get("content", "")

                # Only add if not already saved
                if title not in existing_titles:
                    all_pages_data.append({
                        "title": title,
                        "wikitext": wikitext
                    })
                    existing_titles.add(title)
                    new_items_count += 1
            
            if new_items_count > 0:
                # Write progress back to disk
                logger.info(f"Saving {len(all_pages_data)} pages to {OUTPUT_FILE} (Added {new_items_count} new)")
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_pages_data, f, indent=2)

    logger.info(f"Done! Total saved: {len(all_pages_data)}")

if __name__ == "__main__":
    main()
