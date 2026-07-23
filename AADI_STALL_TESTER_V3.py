#!/usr/bin/env python3
"""Aadi Stall API Key Tester V3. Uses no Google login and no HMAC."""

import json
import sys

try:
    import requests
except ImportError as error:
    raise SystemExit("Run this once first: python3 -m pip install requests") from error

API_BASE = "https://aadi-street-festival-api-2026.azurewebsites.net/api/festival"
STALL_ID = "STALL-07"
API_KEY = "e53dedb0a4751c0edf04a05b4ddc2ff9d2070d19f06a6ada6278c9f30761d375"


def call_api(path, method="GET", payload=None):
    response = requests.request(
        method,
        f"{API_BASE}{path}",
        headers={"X-Aadi-Api-Key": API_KEY},
        json=payload,
        timeout=20,
    )
    try:
        response_body = response.json()
    except requests.JSONDecodeError:
        response_body = {"error": "invalid_server_response"}
    return response.status_code, response_body


def check_key():
    status, result = call_api("/api-key/status")
    print("AADI STALL API KEY TESTER V3 - NO GOOGLE, NO HMAC")
    print(f"Status: {status}")
    print(json.dumps(result, indent=2))
    if status != 200:
        raise SystemExit(1)


def deduct(token_number, amount, sale_id):
    if len(token_number) != 3 or not token_number.isdigit():
        raise SystemExit("Token number must be exactly three digits, for example 123.")
    try:
        numeric_amount = int(amount)
    except ValueError as error:
        raise SystemExit("Amount must be a whole number.") from error
    if numeric_amount <= 0:
        raise SystemExit("Amount must be greater than zero.")
    if len(sale_id) < 12:
        raise SystemExit("Sale ID must be unique and at least 12 characters.")

    status, result = call_api(
        f"/stalls/{STALL_ID}/deductions",
        method="POST",
        payload={
            "tokenNumber": token_number,
            "amount": numeric_amount,
            "idempotencyKey": sale_id,
        },
    )
    print(f"Status: {status}")
    print(json.dumps(result, indent=2))
    if status != 200:
        raise SystemExit(1)


def main():
    if len(sys.argv) == 1 or sys.argv[1] == "check":
        check_key()
        return
    if sys.argv[1] == "deduct" and len(sys.argv) == 5:
        deduct(sys.argv[2], sys.argv[3], sys.argv[4])
        return
    raise SystemExit(
        "Usage:\n"
        "  python3 AADI_STALL_TESTER_V3.py check\n"
        "  python3 AADI_STALL_TESTER_V3.py deduct 123 10 unique-sale-0001"
    )


if __name__ == "__main__":
    main()
