from .base import *

DEBUG = True

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
]

# Dev convenience: any origin may call the API locally (Vite/webpack dev
# servers use arbitrary ports). Production must set CORS_ALLOWED_ORIGINS.
CORS_ALLOW_ALL_ORIGINS = True
