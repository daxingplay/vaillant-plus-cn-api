"""Define package errors."""


class VaillantError(Exception):
    """Define a base error."""

    pass


class RequestError(VaillantError):
    """Define an error related to invalid requests."""

    pass

class InvalidTokenError(VaillantError):
    """Define an error related to login issues.
       This error is only used internally.
    """
    pass

class InvalidCredentialsError(VaillantError):
    """Define an error related to wrong username and password combination.
    """
    pass

class InvalidAuthError(VaillantError):
    """Define an error related to login issues. 
       Usually means token expired.
       Should try to re-login to retrieve a new token.
    """
    pass

class WebsocketServerClosedConnectionError(VaillantError):
    """Define an error when websocket server closed the connection."""
    pass

class WebsocketError(VaillantError):
    """Define an error related to generic websocket errors."""

    pass
