import os

# Tests talk to the app over plain HTTP, where browsers (and httpx) drop Secure cookies.
os.environ["TRACKFOLIO_SECURE_COOKIES"] = "false"
