from __future__ import annotations


class StopPropagation(Exception):
    """
    Raise from a handler to stop processing further handlers for the same event.
    """


