# LD2454 controls

`Multi Target Mode` enables multi-target tracking when on and single-target
tracking when off. The component waits for each successful radar ACK before
advancing through enable configuration, set mode and end configuration.
The switch reports the mode acknowledged by the radar, rather than assuming
that transmitting the command succeeded.

An ACK timeout (1.5 seconds per step) or rejection is logged. Failed operations
attempt to leave configuration mode so target reports can resume. Commands
received while another configuration transaction is active are rejected with a
busy warning; retry after that transaction completes.

Protocol reference: `ld2454-通信协议.pdf`, sections 2.2.1–2.2.4 and 2.4.

Regression test: `python tests/test_ld2454_protocol.py` (requires g++).

### Polygon-only software filtering

Position-reporting radars now use only the room polygon for software boundary filtering. Zone Min/Max Distance controls and their persisted globals have been removed from the shared firmware. Legacy `distance_min`/`distance_max` parameters remain accepted for compatibility but no longer affect detection, even with old nonzero values. An empty polygon disables software boundary filtering. Native radar settings and coordinate transforms are unchanged.
