"""Replaced path retained only as a stale-path fixture."""


def route(message: str) -> str:
    return f"legacy:{message}"
