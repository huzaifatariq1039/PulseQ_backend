# Smart Token Backend Package
# Note: Pointing Gunicorn to 'main:app' is recommended to avoid circular imports.
try:
    from main import app
except ImportError:
    pass