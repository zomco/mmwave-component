"""Retired FakeDevice keeper.

R26-A1: that class did not match mwcp.Client, and the hardware probe never
called it. The controlled path is session_flow.SessionFlow. It uses the real
client's hello(), ping(), and call(name, payload).
"""

from session_flow import SessionFlow

__all__ = ["SessionFlow"]
