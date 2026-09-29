from urllib.parse import urlsplit


def endpoint_label(url: str) -> str:
    """Return a log-safe endpoint label without paths, credentials or query data."""
    parsed = urlsplit(url)
    if parsed.hostname:
        if parsed.port:
            return f"{parsed.hostname}:{parsed.port}"
        return parsed.hostname
    return "invalid-endpoint"
