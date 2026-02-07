import os
from dotenv import load_dotenv as _load_env

_load_env()

(
    os.getenv("WIKI_USERNAME", "") + "@" + os.getenv("WIKI_BOT_NAME", ""),
    os.getenv("WIKI_BOT_PASSWORD", ""),
)
