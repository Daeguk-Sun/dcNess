"""Framework-reachable handler registered by the fixture manifest."""


def handle(message: str) -> str:
    return f"handled:{message}"
