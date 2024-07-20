from urllib.parse import unquote, urlparse


def _extract_username_password(url: str) -> tuple[str, str, str]:
    url_components = urlparse(url)
    username, password = url_components.username, url_components.password
    if username and password:
        url_components = url_components._replace(
            netloc=url_components.hostname,
        )

    return username, unquote(password) if password else None, url_components.geturl()


def sanitize_client_opts(client_opts):
    # Sanitize client options.
    if "host" in client_opts:
        username, password, host = _extract_username_password(client_opts["host"])
        client_opts["username"] = username
        client_opts["password"] = password
        client_opts["host"] = host
    return client_opts
