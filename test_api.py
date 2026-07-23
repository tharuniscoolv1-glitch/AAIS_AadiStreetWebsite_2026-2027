#!/usr/bin/env python3
"""
Aadi Festival API Tester — based on AADI_STALL_TESTER_V3 pattern.
Uses X-Aadi-Api-Key header. No HMAC, no Google login required.

Reads base_url and api_key from config.json under 'aadi_festival_api',
or falls back to the tester defaults.

Usage:
  py test_api.py check
  py test_api.py deduct 123 10 unique-sale-id-0001
"""

import json
import sys
import os
import uuid

try:
    import requests
except ImportError as error:
    raise SystemExit("Run this once first: py -m pip install requests") from error

# ---------------------------------------------------------------------------
# Load config from config.json
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

cfg = load_config().get("aadi_festival_api", {})

API_BASE = os.environ.get("AADI_API_BASE_URL", cfg.get(
    "base_url", "https://aadi-street-festival-api-2026.azurewebsites.net/api/festival"
))
API_KEY = os.environ.get("AADI_API_KEY", cfg.get("api_key", ""))
STALL_ID = "STALL-07"   # default stall; change if needed

print("=" * 60)
print("AADI FESTIVAL API TESTER (V3 pattern)")
print("=" * 60)
print(f"Base URL : {API_BASE}")
print(f"Stall ID : {STALL_ID}")
print(f"API Key  : {'<Loaded>' if API_KEY else '<NOT SET — check config.json>'}")
print("=" * 60)

if not API_KEY:
    raise SystemExit(
        "\n[ERROR] api_key is missing.\n"
        "Add it to config.json under aadi_festival_api.api_key\n"
        "or set the AADI_API_KEY environment variable."
    )


# ---------------------------------------------------------------------------
# Core request helper — matches AADI_STALL_TESTER_V3 exactly
# ---------------------------------------------------------------------------

def call_api(path, method="GET", payload=None):
    """Send a signed request using the X-Aadi-Api-Key header."""
    response = requests.request(
        method,
        f"{API_BASE}{path}",
        headers={"X-Aadi-Api-Key": API_KEY},
        json=payload,
        timeout=20,
    )
    try:
        response_body = response.json()
    except requests.exceptions.JSONDecodeError:
        response_body = {"error": "invalid_server_response", "raw": response.text[:200]}
    return response.status_code, response_body


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------

def check_key():
    """Verify the API key is valid and show its permissions."""
    print("\n[1] Checking API key status...")
    status, result = call_api("/api-key/status")
    print(f"    Status  : {status}")
    print(f"    Response: {json.dumps(result, indent=4)}")
    if status != 200:
        raise SystemExit("[FAILED] Key check returned non-200. Fix the key before proceeding.")
    print("[OK] Key is valid.\n")
    return result


def deduct(token_number, amount, sale_id):
    """
    Submit a deduction for a token at the configured stall.

    token_number : exactly 3 digits, e.g. '123'
    amount       : positive whole number (int)
    sale_id      : unique string, at least 12 characters
    """
    # --- validation (matches V3 tester rules) ---
    if len(token_number) != 3 or not token_number.isdigit():
        raise SystemExit("Token number must be exactly three digits, e.g. 123.")
    try:
        numeric_amount = int(amount)
    except (ValueError, TypeError) as error:
        raise SystemExit("Amount must be a whole number.") from error
    if numeric_amount <= 0:
        raise SystemExit("Amount must be greater than zero.")
    if len(sale_id) < 12:
        raise SystemExit("Sale ID must be unique and at least 12 characters.")

    print(f"\n[2] Submitting deduction: token={token_number}, amount={numeric_amount}, key={sale_id}")
    status, result = call_api(
        f"/stalls/{STALL_ID}/deductions",
        method="POST",
        payload={
            "tokenNumber": token_number,
            "amount": numeric_amount,
            "idempotencyKey": sale_id,
        },
    )
    print(f"    Status  : {status}")
    print(f"    Response: {json.dumps(result, indent=4)}")

    if status == 200 and result.get("status") == "approved":
        print("[OK] Deduction approved.")
    elif status == 409 and result.get("status") == "declined":
        print("[INFO] Deduction declined (insufficient funds).")
    elif status == 409:
        print("[WARN] 409 conflict — idempotency key reused with different data or duplicate.")
    else:
        print(f"[FAILED] Unexpected status {status}.")
        raise SystemExit(1)


def run_full_suite():
    """Run all available tests and report results."""
    print("\nRunning full test suite...\n" + "-" * 40)

    # 1. Key status
    key_info = check_key()
    stall_ids = key_info.get("stallIds", [STALL_ID])
    print(f"    Permitted stalls : {stall_ids}")
    print(f"    Permissions      : {key_info.get('permissions', [])}")

    # 2. Test deduction with a dummy token
    # Use a unique idempotency key each run so we don't hit 409 on retries
    sale_id = f"test-deduct-{uuid.uuid4().hex[:20]}"
    deduct("001", 1, sale_id)

    # 3. Retry identical deduction — should return same result, not double-charge
    print("\n[3] Retrying same deduction (idempotency check)...")
    status, result = call_api(
        f"/stalls/{STALL_ID}/deductions",
        method="POST",
        payload={
            "tokenNumber": "001",
            "amount": 1,
            "idempotencyKey": sale_id,
        },
    )
    print(f"    Status  : {status}")
    print(f"    Response: {json.dumps(result, indent=4)}")
    if status == 200:
        print("[OK] Retry returned 200 (idempotent — no double deduction).")
    else:
        print(f"[INFO] Retry returned {status} — check if that is expected.")

    print("\n" + "=" * 60)
    print("Test suite complete.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) == 1 or sys.argv[1] == "check":
        check_key()
        return

    if sys.argv[1] == "deduct" and len(sys.argv) == 5:
        deduct(sys.argv[2], sys.argv[3], sys.argv[4])
        return

    if sys.argv[1] == "suite":
        run_full_suite()
        return

    raise SystemExit(
        "Usage:\n"
        "  py test_api.py check\n"
        "  py test_api.py deduct <3-digit-token> <amount> <unique-sale-id>\n"
        "  py test_api.py suite\n\n"
        "Examples:\n"
        "  py test_api.py check\n"
        "  py test_api.py deduct 123 50 unique-sale-id-0001\n"
        "  py test_api.py suite"
    )


if __name__ == "__main__":
    main()
