import os

OWNER = "CleverRaven"
REPO = "Cataclysm-DDA"
USE_PROXY = True
HTTP_PROXY = "http://127.0.0.1:10809"
HTTPS_PROXY = "http://127.0.0.1:10809"

ENABLE_SOUNDS = True

# Linux and OSX
TERMINAL_CHAR = "graphics"  # curses or tiles

CHECK_UPDATES = True

# Read the GitHub token from the environment instead of hardcoding it.
# A token was previously hardcoded here only in the working tree (never
# committed to git), but it has been shared in conversation — revoke it at
# https://github.com/settings/tokens. If you need one, set it via
#   set CDDA_GITHUB_TOKEN=...   before running.
# Public-repo release lookups also work without a token (lower rate limit).
GITHUB_TOKEN = os.environ.get("CDDA_GITHUB_TOKEN", "")
