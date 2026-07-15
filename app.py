"""
app.py — LAN Flask Transaction Management App
==============================================
Architecture:
  - users.db   → table 'cards'    (ID TEXT PK, Balance REAL)
  - stalls.db  → table 'inventory' (Stall_ID TEXT, Product_Name TEXT, Price REAL)

Run: python app.py
Access: http://<your-LAN-ip>:5000
"""

import sqlite3
import os
import socket
import json
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
USERS_DB   = os.path.join(BASE_DIR, "users.db")
STALLS_DB  = os.path.join(BASE_DIR, "stalls.db")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PORT       = 5000


# ---------------------------------------------------------------------------
# Config Loading
# ---------------------------------------------------------------------------

def load_config():
    """Load config.json; return defaults if file is missing."""
    defaults = {"admin_password": "admin123", "secret_key": "dev-secret-key"}
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            defaults.update(data)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults

CONFIG = load_config()
app = Flask(__name__)
app.secret_key = CONFIG["secret_key"]


# ---------------------------------------------------------------------------
# LAN IP Detection
# ---------------------------------------------------------------------------

def get_wifi_ssids():
    """Return a dictionary mapping adapter name to its connected Wi-Fi SSID on Windows."""
    ssids = {}
    if os.name == "nt":
        try:
            import subprocess
            import re
            output = subprocess.check_output("netsh wlan show interfaces", shell=True, text=True, errors="ignore")
            current_name = None
            for line in output.splitlines():
                name_match = re.search(r"^\s*Name\s*:\s*(.*)$", line)
                if name_match:
                    current_name = name_match.group(1).strip()
                ssid_match = re.search(r"^\s*SSID\s*:\s*(.*)$", line)
                if ssid_match and current_name:
                    ssid = ssid_match.group(1).strip()
                    if ssid:
                        ssids[current_name] = ssid
        except Exception:
            pass
    return ssids


def get_lan_ips_detailed():
    """
    Return a list of tuples: (ip, network_label) of all non-loopback IPv4 addresses.
    Uses connected Wi-Fi SSIDs for wireless networks, falls back to interface names.
    """
    wifi_ssids = get_wifi_ssids()
    details = []

    # Method 1: psutil (cross-platform, reliable)
    try:
        import psutil
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if not ip.startswith("127."):
                        label = wifi_ssids.get(interface, interface)
                        details.append((ip, label))
        if details:
            # Remove duplicates and sort
            unique_details = list(dict.fromkeys(details).keys())
            return sorted(unique_details, key=lambda x: x[0])
    except Exception:
        pass

    # Method 2: windows-specific ipconfig fallback
    if os.name == "nt":
        try:
            import subprocess
            import re
            output = subprocess.check_output("ipconfig", shell=True, text=True, errors="ignore")
            current_adapter = "Unknown Adapter"
            for line in output.splitlines():
                adapter_match = re.match(r"^(?:Ethernet adapter|Wireless LAN adapter|Adapter)\s+(.*?):", line)
                if adapter_match:
                    current_adapter = adapter_match.group(1).strip()
                elif "IPv4 Address" in line or "IP Address" in line:
                    ip_match = re.search(r":\s*([\d\.]+)", line)
                    if ip_match:
                        ip = ip_match.group(1).strip()
                        if not ip.startswith("127."):
                            label = wifi_ssids.get(current_adapter, current_adapter)
                            details.append((ip, label))
            if details:
                unique_details = list(dict.fromkeys(details).keys())
                return sorted(unique_details, key=lambda x: x[0])
        except Exception:
            pass

    # Method 3: Socket connection route-based fallback (gets primary outbound IP)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if not primary_ip.startswith("127."):
            details.append((primary_ip, "LAN Connection"))
    except Exception:
        pass

    # Method 4: Hostname resolution fallback
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                details.append((ip, "Network Adapter"))
    except Exception:
        pass

    if details:
        unique_details = list(dict.fromkeys(details).keys())
        return sorted(unique_details, key=lambda x: x[0])
    return [("127.0.0.1", "Loopback")]


def get_lan_ips():
    """Return a simple list of IP strings for retro-compatibility."""
    return [item[0] for item in get_lan_ips_detailed()]



# Compute once at import time; also refreshed on every request via context processor
_LAN_IPS = get_lan_ips()


# ---------------------------------------------------------------------------
# Template Context Processor — injects lan_ips into EVERY template
# ---------------------------------------------------------------------------

@app.context_processor
def inject_network_info():
    """Makes `lan_ips`, `lan_ips_detailed`, `port`, and `unlocked` available in all Jinja2 templates."""
    return {
        "lan_ips":          get_lan_ips(),
        "lan_ips_detailed": get_lan_ips_detailed(),
        "port":             PORT,
        "unlocked":         session.get("unlocked", False),
    }



# ---------------------------------------------------------------------------
# Auth Helper
# ---------------------------------------------------------------------------

def require_unlocked():
    """
    Returns a JSON error response if the session is not unlocked.
    Use this at the top of any mutating API route.
    Returns None if access is granted.
    """
    if not session.get("unlocked", False):
        return jsonify({"ok": False, "message": "Locked. Enter the admin password first.", "auth": False}), 403
    return None



# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

def get_users_conn():
    """Return a connection to the Users/Cards database."""
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    return conn


def get_stalls_conn():
    """Return a connection to the Stalls/Inventory database."""
    conn = sqlite3.connect(STALLS_DB)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Initialization — Creates tables and inserts sample data (runs once)
# ---------------------------------------------------------------------------

def init_databases():
    """
    Initialise both SQLite databases with tables and realistic sample data.
    Safe to call on every startup; uses INSERT OR IGNORE so data isn't duplicated.
    """

    # ── Users / Cards database ────────────────────────────────────────────
    with get_users_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                ID      TEXT    PRIMARY KEY,
                Name    TEXT    NOT NULL,
                Balance REAL    NOT NULL DEFAULT 0.0
            )
        """)

        sample_users = [
            ("USR001", "Alice Johnson",  750.00),
            ("USR002", "Bob Smith",      500.00),
            ("USR003", "Carol White",   1200.00),
            ("USR004", "David Brown",    250.00),
            ("USR005", "Eve Davis",       50.00),   # low-balance tester
            ("USR006", "Frank Miller",      0.00),   # zero-balance tester
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO cards (ID, Name, Balance) VALUES (?, ?, ?)",
            sample_users
        )
        conn.commit()

    # ── Stalls / Inventory database ───────────────────────────────────────
    with get_stalls_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                Row_ID       INTEGER PRIMARY KEY AUTOINCREMENT,
                Stall_ID     TEXT    NOT NULL,
                Product_Name TEXT    NOT NULL,
                Price        REAL    NOT NULL DEFAULT 0.0,
                UNIQUE (Stall_ID, Product_Name)
            )
        """)

        sample_inventory = [
            # Stall A — Lighting
            ("STALL-A", "LED Bulb (9W)",         45.00),
            ("STALL-A", "LED Strip (5m)",        180.00),
            ("STALL-A", "Brass Desk Lamp",       350.00),
            ("STALL-A", "Solar Lantern",         275.00),

            # Stall B — Electronics
            ("STALL-B", "USB-C Hub (7-port)",    599.00),
            ("STALL-B", "Wireless Charger",      299.00),
            ("STALL-B", "Bluetooth Speaker",     450.00),
            ("STALL-B", "Power Bank (20000mAh)", 899.00),

            # Stall C — Stationery
            ("STALL-C", "Notebook (A5, 200pg)",   85.00),
            ("STALL-C", "Pen Set (12pc)",          60.00),
            ("STALL-C", "Sticky Notes Bundle",     40.00),
            ("STALL-C", "Canvas Tote Bag",        120.00),

            # Stall D — Food & Beverages
            ("STALL-D", "Fresh Juice (500ml)",    60.00),
            ("STALL-D", "Coffee (Large)",          80.00),
            ("STALL-D", "Sandwich Combo",         120.00),
            ("STALL-D", "Cookie Box (6pc)",        90.00),

            # Stall E — Handicrafts
            ("STALL-E", "Wooden Keychain",        55.00),
            ("STALL-E", "Handmade Candle",        150.00),
            ("STALL-E", "Macramé Wall Art",       320.00),
            ("STALL-E", "Ceramic Mug",            200.00),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO inventory (Stall_ID, Product_Name, Price) VALUES (?, ?, ?)",
            sample_inventory
        )
        conn.commit()

        # ── stalls table (password per stall) ─────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stalls (
                Stall_ID TEXT PRIMARY KEY,
                Password TEXT NOT NULL DEFAULT ''
            )
        """)

        # Seed passwords for the sample stalls (INSERT OR IGNORE so not overwritten)
        sample_stall_passwords = [
            ("STALL-A", "1234"),
            ("STALL-B", "1234"),
            ("STALL-C", "1234"),
            ("STALL-D", "1234"),
            ("STALL-E", "1234"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO stalls (Stall_ID, Password) VALUES (?, ?)",
            sample_stall_passwords
        )
        conn.commit()

    print("[OK] Databases initialised successfully.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """
    Main page.
    Preserves stall_id and any flash messages passed via query params.
    """
    # Pull query-string state (set after a transaction so page reflects outcome)
    selected_stall = request.args.get("stall_id", "")
    message        = request.args.get("message", "")
    msg_type       = request.args.get("msg_type", "")   # "success" | "error" | "warning"

    # If a stall is pre-selected, also load its products
    products = []
    if selected_stall:
        with get_stalls_conn() as conn:
            products = conn.execute(
                "SELECT Product_Name, Price FROM inventory WHERE Stall_ID = ? ORDER BY Product_Name",
                (selected_stall,)
            ).fetchall()

    return render_template(
        "index.html",
        products=products,
        selected_stall=selected_stall,
        message=message,
        msg_type=msg_type,
    )


@app.route("/api/products/<stall_id>")
def api_products(stall_id):
    """
    AJAX endpoint — returns JSON list of products for a given Stall_ID.
    Called by the frontend JS whenever the stall dropdown changes.
    """
    with get_stalls_conn() as conn:
        rows = conn.execute(
            "SELECT Product_Name, Price FROM inventory WHERE Stall_ID = ? ORDER BY Product_Name",
            (stall_id,)
        ).fetchall()

    products = [{"name": r["Product_Name"], "price": r["Price"]} for r in rows]
    return jsonify(products)


@app.route("/api/stalls")
def api_stalls():
    """AJAX endpoint — returns all distinct stall IDs."""
    with get_stalls_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT Stall_ID FROM inventory ORDER BY Stall_ID"
        ).fetchall()
    return jsonify([r["Stall_ID"] for r in rows])


@app.route("/api/verify_stall", methods=["POST"])
def api_verify_stall():
    """
    POST {stall_id, password} → {ok, products: [{name, price}]}
    Verifies the stall password and returns the product list if correct.
    """
    data     = request.get_json()
    stall_id = (data.get("stall_id", "") or "").strip().upper()
    password = (data.get("password", "") or "")

    if not stall_id:
        return jsonify({"ok": False, "message": "Stall ID is required."})

    with get_stalls_conn() as conn:
        stall = conn.execute(
            "SELECT Password FROM stalls WHERE Stall_ID = ?",
            (stall_id,)
        ).fetchone()

        products_rows = conn.execute(
            "SELECT Product_Name, Price FROM inventory WHERE Stall_ID = ? ORDER BY Product_Name",
            (stall_id,)
        ).fetchall()

    if not stall:
        return jsonify({"ok": False, "message": f"Stall '{stall_id}' not found."})

    if stall["Password"] and stall["Password"] != password:
        return jsonify({"ok": False, "message": "Incorrect stall password."})

    if not products_rows:
        return jsonify({"ok": False, "message": f"Stall '{stall_id}' has no products yet."})

    products = [{"name": r["Product_Name"], "price": r["Price"]} for r in products_rows]
    return jsonify({"ok": True, "stall_id": stall_id, "products": products})


@app.route("/api/check_user/<user_id>")
def api_check_user(user_id):
    """
    AJAX endpoint — checks if a user ID exists and returns their balance & name.
    Used for live balance preview before submission.
    """
    with get_users_conn() as conn:
        row = conn.execute(
            "SELECT ID, Name, Balance FROM cards WHERE ID = ?",
            (user_id.upper(),)
        ).fetchone()

    if row:
        return jsonify({"exists": True, "name": row["Name"], "balance": row["Balance"]})
    return jsonify({"exists": False})


@app.route("/submit", methods=["POST"])
def submit():
    """
    Handles transaction form submission.

    Steps:
      1. Validate inputs are present.
      2. Look up the user in users.db.
      3. Look up the product price in stalls.db.
      4. Check balance sufficiency.
      5. Deduct balance and record outcome.
      6. Redirect back to index with preserved stall_id + outcome message.
    """
    user_id       = request.form.get("user_id",       "").strip().upper()
    stall_id      = request.form.get("stall_id",      "").strip().upper()
    stall_password= request.form.get("stall_password","").strip()
    product_name  = request.form.get("product",       "").strip()

    # ── 1. Basic validation ───────────────────────────────────────────
    if not user_id or not stall_id or not product_name:
        return redirect(url_for(
            "index",
            stall_id=stall_id,
            message="All fields are required.",
            msg_type="warning"
        ))

    # ── 1b. Verify stall password server-side ───────────────────────────
    with get_stalls_conn() as stalls_conn:
        stall_row = stalls_conn.execute(
            "SELECT Password FROM stalls WHERE Stall_ID = ?",
            (stall_id,)
        ).fetchone()
    if not stall_row:
        return redirect(url_for("index", stall_id=stall_id,
            message=f"Stall '{stall_id}' not found.", msg_type="error"))
    if stall_row["Password"] and stall_row["Password"] != stall_password:
        return redirect(url_for("index", stall_id=stall_id,
            message="Incorrect stall password.", msg_type="error"))

    # ── 2. Look up user ───────────────────────────────────────────────────
    with get_users_conn() as users_conn:
        user = users_conn.execute(
            "SELECT ID, Name, Balance FROM cards WHERE ID = ?",
            (user_id,)
        ).fetchone()

    if not user:
        return redirect(url_for(
            "index",
            stall_id=stall_id,
            message=f"✗ Card ID '{user_id}' not found. Please try again.",
            msg_type="error"
        ))

    # ── 3. Look up product & price ────────────────────────────────────────
    with get_stalls_conn() as stalls_conn:
        product = stalls_conn.execute(
            "SELECT Product_Name, Price FROM inventory WHERE Stall_ID = ? AND Product_Name = ?",
            (stall_id, product_name)
        ).fetchone()

    if not product:
        return redirect(url_for(
            "index",
            stall_id=stall_id,
            message=f"✗ Product '{product_name}' not found in {stall_id}.",
            msg_type="error"
        ))

    price           = product["Price"]
    current_balance = user["Balance"]

    # ── 4. Check balance ──────────────────────────────────────────────────
    if current_balance < price:
        shortfall = price - current_balance
        return redirect(url_for(
            "index",
            stall_id=stall_id,
            message=(
                f"✗ Insufficient balance for {user['Name']} ({user_id}). "
                f"Balance: ₹{current_balance:.2f} | "
                f"Required: ₹{price:.2f} | "
                f"Shortfall: ₹{shortfall:.2f}"
            ),
            msg_type="error"
        ))

    # ── 5. Deduct balance ─────────────────────────────────────────────────
    new_balance = current_balance - price
    with get_users_conn() as users_conn:
        users_conn.execute(
            "UPDATE cards SET Balance = ? WHERE ID = ?",
            (new_balance, user_id)
        )
        users_conn.commit()

    # ── 6. Redirect with success message ──────────────────────────────────
    return redirect(url_for(
        "index",
        stall_id=stall_id,   # ← Stall_ID is PRESERVED here
        message=(
            f"✔ Transaction Successful! "
            f"{user['Name']} ({user_id}) purchased '{product_name}' "
            f"from {stall_id} for ₹{price:.2f}. "
            f"Remaining Balance: ₹{new_balance:.2f}"
        ),
        msg_type="success"
    ))


@app.route("/admin/users")
def admin_users():
    """
    Simple admin view — lists all users and their current balances.
    Protected with authentication: only admins can view.
    """
    if not session.get("unlocked"):
        return redirect(url_for("admin_login"))
    with get_users_conn() as conn:
        users = conn.execute(
            "SELECT ID, Name, Balance FROM cards ORDER BY ID"
        ).fetchall()
    return render_template("admin_users.html", users=users)




# ---------------------------------------------------------------------------
# Auth Routes — Login / Logout
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """
    GET  — show the login form.
    POST — check password; on success redirect to manage, else show error.
    """
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == CONFIG["admin_password"]:
            session["unlocked"] = True
            return redirect(url_for("admin_manage"))
        error = "Incorrect password. Please try again."

    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    """Clear the session and return to the login page."""
    session.clear()
    return redirect(url_for("admin_login"))


# ---------------------------------------------------------------------------
# Management Panel — Full CRUD for Cards and Stalls/Inventory
# ---------------------------------------------------------------------------

@app.route("/admin/manage")
def admin_manage():
    """
    Management panel — requires login.
    Redirects to /admin/login if the session is not authenticated.
    """
    if not session.get("unlocked"):
        return redirect(url_for("admin_login"))

    with get_users_conn() as conn:
        users = conn.execute(
            "SELECT ID, Name, Balance FROM cards ORDER BY ID"
        ).fetchall()

    with get_stalls_conn() as conn:
        # Group inventory by stall
        rows = conn.execute(
            "SELECT Row_ID, Stall_ID, Product_Name, Price FROM inventory ORDER BY Stall_ID, Product_Name"
        ).fetchall()
        # Fetch passwords for stalls
        pw_rows = conn.execute("SELECT Stall_ID, Password FROM stalls").fetchall()

    passwords = {p["Stall_ID"]: p["Password"] for p in pw_rows}

    # Build a dict: { stall_id: { "password": ..., "products": [ ... ] } }
    stalls_dict = {}
    for r in rows:
        sid = r["Stall_ID"]
        if sid not in stalls_dict:
            stalls_dict[sid] = {
                "password": passwords.get(sid, ""),
                "products": []
            }
        stalls_dict[sid]["products"].append({
            "row_id":  r["Row_ID"],
            "product": r["Product_Name"],
            "price":   r["Price"],
        })

    # Also handle stalls that might exist but have no products yet
    for sid, pw in passwords.items():
        if sid not in stalls_dict:
            stalls_dict[sid] = {
                "password": pw,
                "products": []
            }

    return render_template(
        "admin_manage.html",
        users=users,
        stalls_dict=stalls_dict,
    )


@app.route("/admin/card/add", methods=["POST"])
def admin_card_add():
    """Add a new card. Returns JSON {ok, message}."""
    guard = require_unlocked()
    if guard: return guard
    data    = request.get_json()
    card_id = (data.get("id", "") or "").strip().upper()
    name    = (data.get("name", "") or "").strip()
    balance = data.get("balance", 0)

    if not card_id or not name:
        return jsonify({"ok": False, "message": "Card ID and Name are required."})

    try:
        balance = float(balance)
        if balance < 0:
            return jsonify({"ok": False, "message": "Balance cannot be negative."})
    except (ValueError, TypeError):
        return jsonify({"ok": False, "message": "Balance must be a number."})

    try:
        with get_users_conn() as conn:
            conn.execute(
                "INSERT INTO cards (ID, Name, Balance) VALUES (?, ?, ?)",
                (card_id, name, balance)
            )
            conn.commit()
        return jsonify({"ok": True, "message": f"Card '{card_id}' added successfully."})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "message": f"Card ID '{card_id}' already exists."})


@app.route("/admin/card/edit", methods=["POST"])
def admin_card_edit():
    """Edit a card's name and/or balance. Returns JSON {ok, message, new_balance}."""
    guard = require_unlocked()
    if guard: return guard
    data    = request.get_json()
    card_id = (data.get("id", "") or "").strip().upper()
    name    = (data.get("name", "") or "").strip()
    balance = data.get("balance")

    if not card_id:
        return jsonify({"ok": False, "message": "Card ID is required."})

    # Check existence
    with get_users_conn() as conn:
        row = conn.execute("SELECT * FROM cards WHERE ID = ?", (card_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "message": f"Card '{card_id}' not found."})

    # Use existing values if not provided
    new_name    = name if name else row["Name"]
    try:
        new_balance = float(balance) if balance is not None else row["Balance"]
        if new_balance < 0:
            return jsonify({"ok": False, "message": "Balance cannot be negative."})
    except (ValueError, TypeError):
        return jsonify({"ok": False, "message": "Balance must be a number."})

    with get_users_conn() as conn:
        conn.execute(
            "UPDATE cards SET Name = ?, Balance = ? WHERE ID = ?",
            (new_name, new_balance, card_id)
        )
        conn.commit()

    return jsonify({
        "ok": True,
        "message": f"Card '{card_id}' updated.",
        "new_name": new_name,
        "new_balance": new_balance,
    })


@app.route("/admin/card/delete", methods=["POST"])
def admin_card_delete():
    """Delete a card by ID. Returns JSON {ok, message}."""
    guard = require_unlocked()
    if guard: return guard
    data    = request.get_json()
    card_id = (data.get("id", "") or "").strip().upper()

    if not card_id:
        return jsonify({"ok": False, "message": "Card ID is required."})

    with get_users_conn() as conn:
        affected = conn.execute("DELETE FROM cards WHERE ID = ?", (card_id,)).rowcount
        conn.commit()

    if affected:
        return jsonify({"ok": True, "message": f"Card '{card_id}' deleted."})
    return jsonify({"ok": False, "message": f"Card '{card_id}' not found."})


# ── Stall / Product Management API ───────────────────────────────────────

@app.route("/admin/product/add", methods=["POST"])
def admin_product_add():
    """Add a new product to a stall. Returns JSON {ok, message, row_id}."""
    guard = require_unlocked()
    if guard: return guard
    data         = request.get_json()
    stall_id     = (data.get("stall_id", "") or "").strip()
    product_name = (data.get("product_name", "") or "").strip()
    price        = data.get("price", 0)

    if not stall_id or not product_name:
        return jsonify({"ok": False, "message": "Stall ID and Product Name are required."})

    try:
        price = float(price)
        if price < 0:
            return jsonify({"ok": False, "message": "Price cannot be negative."})
    except (ValueError, TypeError):
        return jsonify({"ok": False, "message": "Price must be a number."})

    try:
        with get_stalls_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO inventory (Stall_ID, Product_Name, Price) VALUES (?, ?, ?)",
                (stall_id, product_name, price)
            )
            conn.commit()
            row_id = cursor.lastrowid
            # Ensure the stall has a row in the stalls table (default empty password)
            conn.execute(
                "INSERT OR IGNORE INTO stalls (Stall_ID, Password) VALUES (?, '')",
                (stall_id,)
            )
            conn.commit()
        return jsonify({
            "ok": True,
            "message": f"'{product_name}' added to {stall_id}.",
            "row_id": row_id,
        })
    except sqlite3.IntegrityError:
        return jsonify({
            "ok": False,
            "message": f"'{product_name}' already exists in {stall_id}."
        })


@app.route("/admin/product/edit", methods=["POST"])
def admin_product_edit():
    """Edit a product's name and/or price by Row_ID. Returns JSON {ok, message}."""
    guard = require_unlocked()
    if guard: return guard
    data         = request.get_json()
    row_id       = data.get("row_id")
    product_name = (data.get("product_name", "") or "").strip()
    price        = data.get("price")

    if not row_id:
        return jsonify({"ok": False, "message": "Row ID is required."})

    with get_stalls_conn() as conn:
        row = conn.execute(
            "SELECT * FROM inventory WHERE Row_ID = ?", (row_id,)
        ).fetchone()

    if not row:
        return jsonify({"ok": False, "message": "Product not found."})

    new_name  = product_name if product_name else row["Product_Name"]
    try:
        new_price = float(price) if price is not None else row["Price"]
        if new_price < 0:
            return jsonify({"ok": False, "message": "Price cannot be negative."})
    except (ValueError, TypeError):
        return jsonify({"ok": False, "message": "Price must be a number."})

    try:
        with get_stalls_conn() as conn:
            conn.execute(
                "UPDATE inventory SET Product_Name = ?, Price = ? WHERE Row_ID = ?",
                (new_name, new_price, row_id)
            )
            conn.commit()
        return jsonify({
            "ok": True,
            "message": f"Product updated successfully.",
            "new_name": new_name,
            "new_price": new_price,
        })
    except sqlite3.IntegrityError:
        return jsonify({
            "ok": False,
            "message": f"'{new_name}' already exists in this stall."
        })


@app.route("/admin/product/delete", methods=["POST"])
def admin_product_delete():
    """Delete a single product row by Row_ID. Returns JSON {ok, message}."""
    guard = require_unlocked()
    if guard: return guard
    data   = request.get_json()
    row_id = data.get("row_id")

    if not row_id:
        return jsonify({"ok": False, "message": "Row ID is required."})

    with get_stalls_conn() as conn:
        affected = conn.execute(
            "DELETE FROM inventory WHERE Row_ID = ?", (row_id,)
        ).rowcount
        conn.commit()

    if affected:
        return jsonify({"ok": True, "message": "Product deleted."})
    return jsonify({"ok": False, "message": "Product not found."})


@app.route("/admin/stall/delete", methods=["POST"])
def admin_stall_delete():
    """Delete all products for a given Stall_ID and remove from stalls table."""
    guard = require_unlocked()
    if guard: return guard
    data     = request.get_json()
    stall_id = (data.get("stall_id", "") or "").strip()

    if not stall_id:
        return jsonify({"ok": False, "message": "Stall ID is required."})

    with get_stalls_conn() as conn:
        affected = conn.execute(
            "DELETE FROM inventory WHERE Stall_ID = ?", (stall_id,)
        ).rowcount
        conn.execute("DELETE FROM stalls WHERE Stall_ID = ?", (stall_id,))
        conn.commit()

    if affected:
        return jsonify({"ok": True, "message": f"Stall '{stall_id}' and all its products deleted."})
    return jsonify({"ok": False, "message": f"Stall '{stall_id}' not found."})


@app.route("/admin/stall/set_password", methods=["POST"])
def admin_stall_set_password():
    """Set or update the password for a stall. Returns JSON {ok, message}."""
    guard = require_unlocked()
    if guard: return guard
    data     = request.get_json()
    stall_id = (data.get("stall_id", "") or "").strip()
    password = (data.get("password", "") or "")

    if not stall_id:
        return jsonify({"ok": False, "message": "Stall ID is required."})

    with get_stalls_conn() as conn:
        # Upsert: update if exists, insert if not
        conn.execute(
            "INSERT INTO stalls (Stall_ID, Password) VALUES (?, ?) "
            "ON CONFLICT(Stall_ID) DO UPDATE SET Password = excluded.Password",
            (stall_id, password)
        )
        conn.commit()

    return jsonify({"ok": True, "message": f"Password for '{stall_id}' updated."})


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_databases()     # Always init/verify DB on startup
    ip_details = get_lan_ips_detailed()
    print("\n" + "-"*60)
    print("  LAN Transaction App -- Running")
    print("  Local  : http://127.0.0.1:" + str(PORT))
    print("  Network addresses (share any of these):")
    for ip, net_name in ip_details:
        print(f"    ->  http://{ip}:{PORT}   ({net_name})")
    print("-"*60 + "\n")
    app.run(host="0.0.0.0", port=PORT, debug=True)

