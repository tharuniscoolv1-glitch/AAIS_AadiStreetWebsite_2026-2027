"""Configuration for connector.py.

Run connector.py on every server PC.  Set one Ethernet-connected PC to
``role = \"gateway\"`` (the machine with reliable internet) and set the other
PCs to ``role = \"client\"`` with that PC's Ethernet IP in ``gateway_url``.

For every PC, set config.json -> aadi_festival_api -> base_url to:
    http://127.0.0.1:5100/api/festival

This file is deliberately separate from app.py and config.json so the relay can
be configured or restarted independently of the stall application.
"""

CONFIG = {
    # "gateway" proxies to Azure. "client" tries Azure first, then uses the
    # Ethernet gateway if the direct internet request fails.
    "role": "gateway",

    # Address on which this connector listens.  Use 0.0.0.0 so other PCs on
    # the Ethernet network can reach a gateway connector.
    "listen_host": "0.0.0.0",
    "listen_port": 5100,

    # The real API URL. Do not put Cosmos keys or connection strings here.
    "upstream_base_url": "https://aadi-street-festival-api-2026.azurewebsites.net/api/festival",

    # Used only when role is "client". Replace 192.168.50.10 with the
    # Ethernet IPv4 address of the PC configured as role "gateway".
    "gateway_url": "http://192.168.50.10:5100",

    # Direct Azure attempts made by client connectors before using the gateway.
    # Set false on PCs known to have no internet, to relay immediately.
    "try_direct_upstream": True,

    # Connection/request limits in seconds.
    "connect_timeout_seconds": 4,
    "request_timeout_seconds": 25,

    # Optional shared secret between client connectors and the gateway.
    # Leave blank to disable connector-to-connector authentication. If set,
    # use the exact same value on every connector_config.py file.
    "shared_secret": "",
}
