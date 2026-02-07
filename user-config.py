"""user-config.py is used to setup the .env credentials to be used by PyWikiBot"""

import os
from dotenv import load_dotenv as _load_env

_load_env()

mylang = "en"
family = "wikipedia"
usernames["wikipedia"]["en"] = os.getenv("WIKI_USERNAME", "")

# Throttle settings to help with rate limiting
maxthrottle = (
    60  # Maximum number of seconds to wait between API requests when throttled
)
put_throttle = 1  # Minimum delay in seconds between write (PUT/POST) requests to avoid overwhelming the API
