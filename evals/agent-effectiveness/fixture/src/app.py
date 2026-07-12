"""Runtime entrypoint for the notification fixture."""

from notifications.dispatcher import dispatch


def main(message: str) -> str:
    return dispatch(message)
