"""Ethernet relay for the Aadi Festival API.

This service lets stall-server PCs share a single internet-connected gateway.
It is intentionally independent of app.py.  Start it on every PC before
starting the stall app:

    py connector.py

Then set the existing ``aadi_festival_api.base_url`` in config.json on every
PC to ``http://127.0.0.1:5100/api/festival``.
"""

from __future__ import annotations

import hmac
import logging

import requests
from flask import Flask, Response, jsonify, request

from connector_config import CONFIG


app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("aadi-connector")

HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length",
}


def _timeout() -> tuple[int, int]:
    return (int(CONFIG["connect_timeout_seconds"]), int(CONFIG["request_timeout_seconds"]))


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _forward_headers(include_secret: bool = False) -> dict[str, str]:
    excluded = HOP_BY_HOP_HEADERS | {"x-aadi-connector-key"}
    headers = {key: value for key, value in request.headers.items() if key.lower() not in excluded}
    if include_secret and CONFIG.get("shared_secret"):
        headers["X-Aadi-Connector-Key"] = CONFIG["shared_secret"]
    return headers


def _request(target: str, include_secret: bool = False) -> requests.Response:
    return requests.request(
        method=request.method,
        url=target,
        params=request.args,
        data=request.get_data(),
        headers=_forward_headers(include_secret),
        timeout=_timeout(),
        allow_redirects=False,
    )


def _response(upstream: requests.Response) -> Response:
    headers = [(key, value) for key, value in upstream.headers.items() if key.lower() not in HOP_BY_HOP_HEADERS]
    return Response(upstream.content, status=upstream.status_code, headers=headers)


def _gateway_authorized() -> bool:
    secret = CONFIG.get("shared_secret", "")
    if not secret:
        return True
    supplied = request.headers.get("X-Aadi-Connector-Key", "")
    return hmac.compare_digest(supplied, secret)


def _proxy(path: str) -> Response:
    role = CONFIG.get("role", "gateway").lower()
    if role not in {"gateway", "client"}:
        return jsonify(error="invalid_connector_role"), 500

    if role == "gateway":
        if not _gateway_authorized():
            return jsonify(error="connector_unauthorized"), 401
        try:
            return _response(_request(_url(CONFIG["upstream_base_url"], path)))
        except requests.RequestException as exc:
            LOG.warning("Gateway cannot reach upstream: %s", exc)
            return jsonify(error="upstream_unavailable", detail="Gateway cannot reach the festival API."), 503

    # A client can use its own internet, but falls back to the Ethernet gateway.
    if CONFIG.get("try_direct_upstream", True):
        try:
            return _response(_request(_url(CONFIG["upstream_base_url"], path)))
        except requests.RequestException as exc:
            LOG.info("Direct upstream unavailable; trying Ethernet gateway: %s", exc)

    gateway = CONFIG.get("gateway_url", "").strip()
    if not gateway:
        return jsonify(error="gateway_not_configured"), 503
    try:
        return _response(_request(_url(gateway, f"api/festival/{path}"), include_secret=True))
    except requests.RequestException as exc:
        LOG.warning("Ethernet gateway unavailable: %s", exc)
        return jsonify(error="connector_offline", detail="Neither direct internet nor Ethernet gateway is available."), 503


@app.get("/connector/health")
def health() -> Response:
    """Local status endpoint; it does not contact Azure."""
    return jsonify(
        ok=True,
        role=CONFIG.get("role", "gateway"),
        upstream=CONFIG.get("upstream_base_url"),
        gateway=CONFIG.get("gateway_url") if CONFIG.get("role", "").lower() == "client" else None,
    )


@app.route("/api/festival", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.route("/api/festival/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def festival_api(path: str = "") -> Response:
    """Transparent relay for the festival API paths used by app.py."""
    if request.method == "OPTIONS":
        return Response(status=204)
    return _proxy(path)


if __name__ == "__main__":
    host = CONFIG["listen_host"]
    port = int(CONFIG["listen_port"])
    LOG.info("Starting %s connector on http://%s:%s", CONFIG.get("role", "gateway"), host, port)
    app.run(host=host, port=port, debug=False, threaded=True)
