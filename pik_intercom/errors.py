class PikIntercomException(Exception):
    """Base class for exceptions"""


class MalformedDataError(PikIntercomException, ValueError):
    """Received data is malformed"""


class ServerResponseError(PikIntercomException):
    """Error embedded into server response"""
