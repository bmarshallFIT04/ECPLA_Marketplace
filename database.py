import sqlite3
import os
import bcrypt

# Set database path inside the project's 'instance' directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'marketplace.db')
MAX_PASSWORD_LENGTH = 64
MIN_PASSWORD_LENGTH = 6
MAX_USERNAME_LENGTH = 64
MIN_USERNAME_LENGTH = 3
HASH_ROUNDS = 12
DEFAULT_ORDER_STATUS = "Confirmed"
# Shipment statuses a seller can post on an order, in the usual order they happen
ORDER_STATUSES = [
    "Confirmed",
    "Shipped",
    "Arrived at shipping facility",
    "In transit",
    "Out for delivery",
    "Delivered",
    "Delayed",
]
MAX_TRACKING_NUMBER_LENGTH = 64
MAX_ORDER_NOTE_LENGTH = 500
SALT = bcrypt.gensalt(rounds=HASH_ROUNDS) # time to hash increases with rounds

SAVED_SHIPPING_SQL = '''
    CREATE TABLE IF NOT EXISTS saved_shipping (
        shipping_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        full_name TEXT NOT NULL,
        address TEXT NOT NULL,
        is_default INTEGER NOT NULL DEFAULT 0
    )
'''

SAVED_PAYMENT_SQL = '''
    CREATE TABLE IF NOT EXISTS saved_payment (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        card_number TEXT NOT NULL,
        expiration TEXT NOT NULL,
        is_default INTEGER NOT NULL DEFAULT 0
    )
'''


def _upgrade_saved_table(cursor, table, id_column, create_sql, columns):
    """Upgrades an old saved_shipping/saved_payment table (one row per user, keyed by user_id) to the
    multi-entry version. Each user's existing saved entry is copied over and becomes their default."""
    existing_columns = [row[1] for row in cursor.execute(f'PRAGMA table_info({table})')]
    if not existing_columns or id_column in existing_columns:
        return  # table doesn't exist yet, or is already upgraded
    cursor.execute(f'ALTER TABLE {table} RENAME TO {table}_old')
    cursor.execute(create_sql)
    cursor.execute(f'INSERT INTO {table} (user_id, {columns}, is_default) '
                   f'SELECT user_id, {columns}, 1 FROM {table}_old')
    cursor.execute(f'DROP TABLE {table}_old')


def init_db():
    """Initializes the database and creates the products table if it doesn't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            stock_quantity INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Initializes User Accounts database (one row per tag on a product)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    # Initializes Reviews database
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating <= 9),
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL
        )
    ''')

    # Initializes Product Tags database (one row per tag on a product)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_tags (
            tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            UNIQUE (product_id, tag)
        )
    ''')

    # Initializes saved checkout information: each user can save several addresses and cards,
    # and one of each is their default. Older one-per-user tables are upgraded first, keeping their data.
    _upgrade_saved_table(cursor, "saved_shipping", "shipping_id", SAVED_SHIPPING_SQL, "full_name, address")
    _upgrade_saved_table(cursor, "saved_payment", "payment_id", SAVED_PAYMENT_SQL, "card_number, expiration")
    cursor.execute(SAVED_SHIPPING_SQL)
    # The CVV is intentionally never stored; buyers re-enter it for each order
    cursor.execute(SAVED_PAYMENT_SQL)

    # Initializes Shopping Cart table - bryan bermudez
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS cart_items (
                cart_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id)
            )
        ''')

    # Initializes Messages table: email-style messages between two users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            is_read INTEGER NOT NULL DEFAULT 0,
            sender_deleted INTEGER NOT NULL DEFAULT 0,
            recipient_deleted INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # Initializes Blocked Users table: blocker_id has blocked blocked_id's communication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_users (
            blocker_id INTEGER NOT NULL,
            blocked_id INTEGER NOT NULL,
            blocked_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (blocker_id, blocked_id)
        )
    ''')

    # Initializes Orders/Transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_title TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            date TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            full_name TEXT NOT NULL,
            address TEXT NOT NULL,
            total REAL NOT NULL,
            status TEXT NOT NULL
        )
    ''')

    # Initializes Order Updates table: the shipment status history of each order (newest row = current status)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_updates (
            update_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # Adds the tracking number to orders tables created before order tracking existed
    order_columns = [row[1] for row in cursor.execute('PRAGMA table_info(orders)')]
    if 'tracking_number' not in order_columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN tracking_number TEXT')

    # Adds the "deleted" flags to messages tables created before message deletion existed
    message_columns = [row[1] for row in cursor.execute('PRAGMA table_info(messages)')]
    for column in ('sender_deleted', 'recipient_deleted'):
        if column not in message_columns:
            cursor.execute(f'ALTER TABLE messages ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0')

    conn.commit()
    conn.close()

    



def add_product(seller_id, title, description, price, stock_quantity, tags=None):
    """Adds a new product (and any tags) to the database with validation checks."""
    if price < 0.01:
        return {"success": False, "message": "Price must be at least $0.01 (cannot be negative or zero)."}

    if stock_quantity < 0:
        return {"success": False, "message": "Stock quantity cannot be negative."}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (seller_id, title, description, price, stock_quantity)
        VALUES (?, ?, ?, ?, ?)
    ''', (seller_id, title, description, price, stock_quantity))
    product_id = cursor.lastrowid
    cursor.executemany('INSERT INTO product_tags (product_id, tag) VALUES (?, ?)',
                       [(product_id, tag) for tag in clean_tags(tags or [])])
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Product '{title}' added to the database!"}

def remove_product(product_id):
    """Removes a product (and its tags) from the database by its ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE product_id = ?', (product_id,))
    cursor.execute('DELETE FROM product_tags WHERE product_id = ?', (product_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    if rows_affected > 0:
        return {"success": True, "message": f"Product ID {product_id} has been removed."}
    else:
        return {"success": False, "message": f"No product found with ID {product_id}."}


def list_products():
    """Lists all products currently in the database, from every seller, newest first."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT product_id, seller_id, title, price, stock_quantity, description
        FROM products
        ORDER BY product_id DESC
    ''')
    products = cursor.fetchall()
    conn.close()
    return products


def list_best_selling_products(limit=4):
    """Returns the products with the most units sold across all sellers, best seller first.
    If fewer than `limit` products have sales, the rest are filled with the newest unsold products.
    Ties go to the newer product."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.product_id, p.title, p.description, p.price, p.stock_quantity, a.username,
               COALESCE(SUM(o.quantity), 0) AS units_sold
        FROM products p
        LEFT JOIN orders o ON o.product_id = p.product_id
        LEFT JOIN accounts a ON p.seller_id = a.user_id
        GROUP BY p.product_id
        ORDER BY units_sold DESC, p.product_id DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "price": r[3], "stock": r[4],
             "seller_username": r[5], "units_sold": r[6]} for r in rows]


def get_product(product_id):
    """Returns one product (with its tags) as a dict, or None if no product has that ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.product_id, p.seller_id, p.title, p.description, p.price, p.stock_quantity, a.username
        FROM products p
        LEFT JOIN accounts a ON p.seller_id = a.user_id
        WHERE p.product_id = ?
    ''', (product_id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None
    return {"id": row[0], "seller_id": row[1], "title": row[2], "description": row[3],
            "price": row[4], "stock": row[5], "tags": get_product_tags(row[0]),
            "seller_username": row[6]}


def list_products_by_seller(seller_id):
    """Searches and lists products belonging to a specific seller ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT product_id, title, description, price, stock_quantity FROM products WHERE seller_id = ?',
                   (seller_id,))
    products = cursor.fetchall()
    conn.close()
    return products

def add_review(body:str, rating:int, user_id:int, product_id:int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reviews (body, rating, user_id, product_id)
        VALUES (?, ?, ?, ?)
    ''', (body, rating, user_id, product_id))
    conn.commit()
    conn.close()
    return True

# To-do: Validate input with regexx
def validate_input(text: str) -> bool:
    return True

# To-do: Complete add_account()
def add_account(username, password, role):
    username = (username or "").strip()

    '''Input Validation Checks'''
    # Username
    if (len(username) < MIN_USERNAME_LENGTH) or (len(username) > MAX_USERNAME_LENGTH) :
        return {"success": False, "message": f"Username must be between {MIN_USERNAME_LENGTH} and {MAX_USERNAME_LENGTH} characters."}
    elif not validate_input(username):
        return {"success": False, "message": "The username given includes invalid characters."}
    elif get_account(username):
        return {"success": False, "message": f"The username {username} is already taken."}

    # Password
    if (len(password) < MIN_PASSWORD_LENGTH) or (len(password) > MAX_PASSWORD_LENGTH) :
        return {"success": False, "message": f"Password must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters."}
    elif not validate_input(password):
        return {"success": False, "message": "The password given includes invalid characters."}

    # Role
    if (role != "buyer") and (role != "seller"):
        return {"success": False, "message": "Account type must be a Buyer or Seller."}

    # Save account record (the UNIQUE constraint is a backstop if two signups race for the same name)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO accounts (username, password, role)
            VALUES (?, ?, ?)
        ''', (username, bcrypt.hashpw(password.encode('utf-8'), SALT), role))
        conn.commit()
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"The username {username} is already taken."}
    finally:
        conn.close()

    return {"success": True, "message": f"User account {username} has been successfully created."}

# To-do
def remove_account():
    pass

def get_account(username: str):
    """Looks up an account by username, ignoring capitalization ("Seller1" finds "seller1").
    Returns {"user_id", "username", "role"}, or None if no account has that username."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, role FROM accounts WHERE username = ? COLLATE NOCASE',
                   ((username or "").strip(),))
    row = cursor.fetchone()
    conn.close()
    return {"user_id": row[0], "username": row[1], "role": row[2]} if row else None

# Input: An account username and password (unencrypted)
# Output:
#   the success key stores the user_id and role name, and the message key stores the reason for success/failure.
#   If the username/password combo matches, the user's ID and role is returned.
#   If the combo is invalid, a None is returned.
def authenticate(username: str, password: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.user_id, a.password, a.role
        FROM accounts a
        WHERE a.username = ?
    ''', (username,))

    db_fetched = cursor.fetchall()
    if len(db_fetched) == 0:
        return {"success": None, "message": f"The username does not exist, or the password does not match."}

    db_user_id, db_password, db_role = db_fetched[0]
    conn.close()

    # if user exists and hashes are identical
    if db_password and bcrypt.checkpw(password.encode('utf-8'), db_password): 
        return {"success": (db_user_id, db_role), "message": f"User account {username} is successfully logged in."}
    else:
        return {"success": None, "message": f"The username does not exist, or the password does not match."}

# To-do
def get_account_detail(field: str):
    pass


def get_user(user_id: int):
    """Returns an account's public info (ID, username, role) as a dict, or None if no account has that ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, role FROM accounts WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return {"user_id": row[0], "username": row[1], "role": row[2]} if row else None

# Calculates order total, decreases seller's stock, and saves the order
def add_order(user_id: int, product_id: int, quantity: int, address: dict) -> bool:
    # Details for order info
    product = get_product(product_id)
    total = product.get("price") * quantity

    # Create record for the order
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (user_id, product_id, product_title, quantity, address, full_name, total, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, product_id, product["title"], quantity, address["address"], address["full_name"], total, DEFAULT_ORDER_STATUS))

    # Start the order's tracking history with its first status
    cursor.execute('INSERT INTO order_updates (order_id, status) VALUES (?, ?)',
                   (cursor.lastrowid, DEFAULT_ORDER_STATUS))

    # Decrease product's stock by the quantity ordered
    new_stock = product.get("stock") - quantity
    cursor.execute('''
        UPDATE products
        SET stock_quantity = ?
        WHERE product_id = ?;
    ''', (new_stock, product_id))

    conn.commit()
    conn.close()
    return True

# Returns list of order IDs connected to user ID, newest order first.
def get_orders(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.order_id
        FROM orders o
        WHERE o.user_id = ?
        ORDER BY o.order_id DESC
    ''', (user_id,))
    orders = cursor.fetchall()
    conn.close()

    return [order[0] for order in orders] if len(orders) > 0 else []

# Given an ID, returns all order attributes
def get_order_details(order_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # seller_id comes from the product, so it's None if the product has since been removed
    cursor.execute('''
        SELECT o.user_id, o.product_id, o.product_title, o.quantity, o.date, o.address, o.total, o.status,
               p.seller_id, o.tracking_number, o.full_name, a.username
        FROM orders o
        LEFT JOIN products p ON o.product_id = p.product_id
        LEFT JOIN accounts a ON o.user_id = a.user_id
        WHERE o.order_id = ?
    ''', (order_id,))
    order = cursor.fetchall()
    conn.close()

    if len(order) > 0:
        (user_id, product_id, product_title, quantity, date, address, total, status,
         seller_id, tracking_number, full_name, buyer_username) = order[0]
        order_dict = {
            "order_id": order_id,
            "user_id": user_id,
            "buyer_username": buyer_username,  # None for guest orders (placed without an account)
            "product_id": product_id,
            "seller_id": seller_id,
            "tracking_number": tracking_number,
            "full_name": full_name,
            "quantity": quantity,
            "date": date,
            "address": address,
            "total": total,
            "status": status,
            "product_title": product_title
        }
        return order_dict
    else:
        return None


def _is_sellers_order(cursor, order_id, seller_id):
    """Returns True if the order is for one of this seller's products."""
    cursor.execute('''
        SELECT 1 FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.order_id = ? AND p.seller_id = ?
    ''', (order_id, seller_id))
    return cursor.fetchone() is not None


def set_tracking_number(order_id: int, seller_id: int, tracking_number: str) -> dict:
    """Saves (or replaces) the shipping/tracking number on an order. Only the product's seller can do this.
    An empty tracking number removes it."""
    tracking_number = (tracking_number or "").strip()
    if len(tracking_number) > MAX_TRACKING_NUMBER_LENGTH:
        return {"success": False,
                "message": f"Tracking number must be {MAX_TRACKING_NUMBER_LENGTH} characters or fewer."}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if not _is_sellers_order(cursor, order_id, seller_id):
        conn.close()
        return {"success": False, "message": "You can only update orders for your own products."}

    cursor.execute('UPDATE orders SET tracking_number = ? WHERE order_id = ?', (tracking_number or None, order_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Tracking number saved." if tracking_number else "Tracking number removed."}


def add_order_update(order_id: int, seller_id: int, status: str, note: str = "") -> dict:
    """Posts a shipment status update (e.g. "Out for delivery") with an optional note to an order's history,
    and makes it the order's current status. Only the product's seller can do this."""
    note = (note or "").strip()
    if status not in ORDER_STATUSES:
        return {"success": False, "message": "Please choose a valid status."}
    if len(note) > MAX_ORDER_NOTE_LENGTH:
        return {"success": False, "message": f"Note must be {MAX_ORDER_NOTE_LENGTH} characters or fewer."}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if not _is_sellers_order(cursor, order_id, seller_id):
        conn.close()
        return {"success": False, "message": "You can only update orders for your own products."}

    cursor.execute('INSERT INTO order_updates (order_id, status, note) VALUES (?, ?, ?)',
                   (order_id, status, note or None))
    cursor.execute('UPDATE orders SET status = ? WHERE order_id = ?', (status, order_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Status updated to \"{status}\"."}


def get_order_updates(order_id: int) -> list:
    """Returns an order's shipment status history, newest first."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status, note, created_at FROM order_updates
        WHERE order_id = ?
        ORDER BY update_id DESC
    ''', (order_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"status": r[0], "note": r[1], "created_at": r[2]} for r in rows]


def get_seller_sales(seller_id: int) -> dict:
    """Totals for the Seller Analytics section, from every order placed for this seller's products:
    revenue (amount paid), units sold, and number of orders."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COALESCE(SUM(o.total), 0), COALESCE(SUM(o.quantity), 0), COUNT(o.order_id)
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE p.seller_id = ?
    ''', (seller_id,))
    revenue, units_sold, order_count = cursor.fetchone()
    conn.close()
    return {"revenue": revenue, "units_sold": units_sold, "order_count": order_count}


def list_seller_orders(seller_id: int) -> list:
    """Returns every order placed for this seller's products, newest first, with the buyer's username
    and the amount paid."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.order_id, o.product_title, o.quantity, o.date, o.status, o.tracking_number, a.username, o.total
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        LEFT JOIN accounts a ON o.user_id = a.user_id
        WHERE p.seller_id = ?
        ORDER BY o.order_id DESC
    ''', (seller_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"order_id": r[0], "product_title": r[1], "quantity": r[2], "date": r[3], "status": r[4],
             "tracking_number": r[5], "buyer_username": r[6], "total": r[7]} for r in rows]


def has_ordered_from_seller(buyer_id: int, seller_id: int) -> bool:
    """Returns True if the buyer has placed at least one order for one of the seller's products."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.user_id = ? AND p.seller_id = ?
        LIMIT 1
    ''', (buyer_id, seller_id))
    ordered = cursor.fetchone() is not None
    conn.close()
    return ordered


def list_seller_buyers(seller_id: int) -> list:
    """Returns everyone who has ordered one of the seller's products, most recent order first.
    Each entry has the buyer's ID, username, number of orders, and latest order date.
    Guest orders (placed without an account) are left out, since guests can't be messaged."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.user_id, a.username, COUNT(*) AS order_count, MAX(o.date) AS last_order_date
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        JOIN accounts a ON o.user_id = a.user_id
        WHERE p.seller_id = ? AND o.user_id != ?
        GROUP BY o.user_id
        ORDER BY last_order_date DESC
    ''', (seller_id, seller_id))
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": r[0], "username": r[1], "order_count": r[2], "last_order_date": r[3]} for r in rows]

def clean_tags(tags):
    """Trims and lowercases tags, dropping blanks and duplicates while keeping their order."""
    cleaned = []
    for tag in tags:
        tag = str(tag).strip().lower()
        if tag and tag not in cleaned:
            cleaned.append(tag)
    return cleaned


def get_product_tags(product_id):
    """Returns the list of tags on a product, in the order they were added."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT tag FROM product_tags WHERE product_id = ? ORDER BY tag_id', (product_id,))
    tags = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tags


def set_product_tags(product_id, seller_id, tags):
    """Replaces a product's tags with the given list. Handles adding, editing, and removing tags."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM products WHERE product_id = ? AND seller_id = ?', (product_id, seller_id))
    if cursor.fetchone() is None:
        conn.close()
        return {"success": False, "message": f"No product found with ID {product_id} for this seller."}

    tags = clean_tags(tags)
    cursor.execute('DELETE FROM product_tags WHERE product_id = ?', (product_id,))
    cursor.executemany('INSERT INTO product_tags (product_id, tag) VALUES (?, ?)',
                       [(product_id, tag) for tag in tags])
    conn.commit()
    conn.close()
    return {"success": True, "message": "Tags updated.", "tags": tags}


# ----- Saved shipping addresses and cards -----
# A user can save several of each. Exactly one of each is their default, which checkout picks first.

def _delete_saved(table, id_column, user_id, item_id):
    """Removes one of the user's saved entries. If it was their default, their oldest remaining one becomes
    the default. Returns True if something was removed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f'SELECT is_default FROM {table} WHERE user_id = ? AND {id_column} = ?', (user_id, item_id))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return False
    cursor.execute(f'DELETE FROM {table} WHERE user_id = ? AND {id_column} = ?', (user_id, item_id))
    if row[0]:
        cursor.execute(f'''
            UPDATE {table} SET is_default = 1
            WHERE {id_column} = (SELECT MIN({id_column}) FROM {table} WHERE user_id = ?)
        ''', (user_id,))
    conn.commit()
    conn.close()
    return True


def _set_default_saved(table, id_column, user_id, item_id):
    """Makes one of the user's saved entries their default (and un-defaults the rest).
    Returns True if the entry belongs to the user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f'SELECT 1 FROM {table} WHERE user_id = ? AND {id_column} = ?', (user_id, item_id))
    if cursor.fetchone() is None:
        conn.close()
        return False
    cursor.execute(f'UPDATE {table} SET is_default = ({id_column} = ?) WHERE user_id = ?', (item_id, user_id))
    conn.commit()
    conn.close()
    return True


def _has_saved(cursor, table, user_id):
    cursor.execute(f'SELECT 1 FROM {table} WHERE user_id = ? LIMIT 1', (user_id,))
    return cursor.fetchone() is not None


def _shipping_dict(row):
    return {"id": row[0], "full_name": row[1], "address": row[2], "is_default": bool(row[3])}


def list_shipping_addresses(user_id):
    """Returns all of a user's saved addresses, default first, then oldest first."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT shipping_id, full_name, address, is_default FROM saved_shipping
        WHERE user_id = ? ORDER BY is_default DESC, shipping_id
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [_shipping_dict(r) for r in rows]


def get_shipping_address(user_id, shipping_id=None):
    """Returns one of a user's saved addresses as a dict: the given one, or their default if no ID is given.
    Returns None if they have no such address."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if shipping_id is None:
        cursor.execute('''
            SELECT shipping_id, full_name, address, is_default FROM saved_shipping
            WHERE user_id = ? ORDER BY is_default DESC, shipping_id LIMIT 1
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT shipping_id, full_name, address, is_default FROM saved_shipping
            WHERE user_id = ? AND shipping_id = ?
        ''', (user_id, shipping_id))
    row = cursor.fetchone()
    conn.close()
    return _shipping_dict(row) if row else None


def save_shipping_address(user_id, full_name, address):
    """Adds an address to the user's saved addresses. Their first address becomes their default.
    Saving an address they've already saved doesn't create a duplicate."""
    full_name = (full_name or "").strip()
    address = (address or "").strip()
    if not full_name or not address:
        return {"success": False, "message": "Please enter a full name and address."}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT shipping_id FROM saved_shipping
        WHERE user_id = ? AND full_name = ? COLLATE NOCASE AND address = ? COLLATE NOCASE
    ''', (user_id, full_name, address))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {"success": True, "message": "That address is already saved.", "id": existing[0]}

    is_default = 0 if _has_saved(cursor, "saved_shipping", user_id) else 1
    cursor.execute('INSERT INTO saved_shipping (user_id, full_name, address, is_default) VALUES (?, ?, ?, ?)',
                   (user_id, full_name, address, is_default))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "message": "Address saved.", "id": new_id}


def update_shipping_address(user_id, shipping_id, full_name, address):
    """Edits one of the user's saved addresses."""
    full_name = (full_name or "").strip()
    address = (address or "").strip()
    if not full_name or not address:
        return {"success": False, "message": "Please enter a full name and address."}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE saved_shipping SET full_name = ?, address = ? WHERE user_id = ? AND shipping_id = ?',
                   (full_name, address, user_id, shipping_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    if not updated:
        return {"success": False, "message": "That address wasn't found."}
    return {"success": True, "message": "Address updated."}


#Bryan Bermudez- Remove a buyer's saved shipping address
def delete_shipping_address(user_id, shipping_id):
    """Removes one of the user's saved addresses. Returns True if it was removed."""
    return _delete_saved("saved_shipping", "shipping_id", user_id, shipping_id)


def set_default_shipping_address(user_id, shipping_id):
    """Makes one of the user's saved addresses the one checkout picks first."""
    return _set_default_saved("saved_shipping", "shipping_id", user_id, shipping_id)


def validate_card(card_number, expiration):
    """Only checks that a card number and expiration were entered. Their format is deliberately not checked,
    so testing with made-up cards like "1234" is easy. Returns (trimmed card number, error message or None)."""
    card_number = (card_number or "").strip()
    if not card_number or not (expiration or "").strip():
        return card_number, "Please enter a card number and expiration date."
    return card_number, None


def _payment_dict(row):
    return {"id": row[0], "card_number": row[1], "last4": row[1][-4:], "expiration": row[2],
            "is_default": bool(row[3])}


def list_payment_methods(user_id):
    """Returns all of a user's saved cards, default first, then oldest first."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT payment_id, card_number, expiration, is_default FROM saved_payment
        WHERE user_id = ? ORDER BY is_default DESC, payment_id
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [_payment_dict(r) for r in rows]


def get_payment_info(user_id, payment_id=None):
    """Returns one of a user's saved cards as a dict: the given one, or their default if no ID is given.
    Returns None if they have no such card."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if payment_id is None:
        cursor.execute('''
            SELECT payment_id, card_number, expiration, is_default FROM saved_payment
            WHERE user_id = ? ORDER BY is_default DESC, payment_id LIMIT 1
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT payment_id, card_number, expiration, is_default FROM saved_payment
            WHERE user_id = ? AND payment_id = ?
        ''', (user_id, payment_id))
    row = cursor.fetchone()
    conn.close()
    return _payment_dict(row) if row else None


def save_payment_info(user_id, card_number, expiration):
    """Adds a card to the user's saved cards. Their first card becomes their default.
    Saving a card number that's already saved updates its expiration instead of duplicating it.
    The CVV is never saved."""
    card_number, error = validate_card(card_number, expiration)
    if error:
        return {"success": False, "message": error}
    expiration = expiration.strip()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT payment_id FROM saved_payment WHERE user_id = ? AND card_number = ?',
                   (user_id, card_number))
    existing = cursor.fetchone()
    if existing:
        cursor.execute('UPDATE saved_payment SET expiration = ? WHERE payment_id = ?', (expiration, existing[0]))
        conn.commit()
        conn.close()
        return {"success": True, "message": "That card is already saved; its expiration date was updated.",
                "id": existing[0]}

    is_default = 0 if _has_saved(cursor, "saved_payment", user_id) else 1
    cursor.execute('INSERT INTO saved_payment (user_id, card_number, expiration, is_default) VALUES (?, ?, ?, ?)',
                   (user_id, card_number, expiration, is_default))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "message": "Card saved.", "id": new_id}


#Bryan Bermudez- Remove a buyer's saved payment information
def delete_payment_info(user_id, payment_id):
    """Removes one of the user's saved cards. Returns True if it was removed."""
    return _delete_saved("saved_payment", "payment_id", user_id, payment_id)


def set_default_payment(user_id, payment_id):
    """Makes one of the user's saved cards the one checkout picks first."""
    return _set_default_saved("saved_payment", "payment_id", user_id, payment_id)

    #Shopping car functions
def add_to_cart(user_id, product_id, quantity=1):
    """Adds a product to a user's cart or increments quantity if it already exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if item already exists in user's cart
    cursor.execute('''
        SELECT quantity FROM cart_items WHERE user_id = ? AND product_id = ?
    ''', (user_id, product_id))
    row = cursor.fetchone()

    if row:
        new_qty = row[0] + quantity
        cursor.execute('''
            UPDATE cart_items SET quantity = ? WHERE user_id = ? AND product_id = ?
        ''', (new_qty, user_id, product_id))
    else:
        cursor.execute('''
            INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)
        ''', (user_id, product_id, quantity))

    conn.commit()
    conn.close()
    return {"success": True, "message": "Product added to cart."}


def get_cart_items(user_id):
    """Returns all items in a buyer's cart with product details."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.cart_item_id, p.product_id, p.title, p.price, c.quantity, p.stock_quantity
        FROM cart_items c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "cart_item_id": r[0],
            "product_id": r[1],
            "title": r[2],
            "price": r[3],
            "quantity": r[4],
            "stock_quantity": r[5]
        }
        for r in rows
    ]


def update_cart_quantity(cart_item_id, quantity):
    """Updates or removes an item quantity in the cart."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if quantity <= 0:
        cursor.execute('DELETE FROM cart_items WHERE cart_item_id = ?', (cart_item_id,))
    else:
        cursor.execute('UPDATE cart_items SET quantity = ? WHERE cart_item_id = ?', (quantity, cart_item_id))
    conn.commit()
    conn.close()
    return {"success": True}


def remove_from_cart(cart_item_id):
    """Removes an item from the cart completely."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart_items WHERE cart_item_id = ?', (cart_item_id,))
    conn.commit()
    conn.close()
    return {"success": True}


def clear_cart(user_id):
    """Removes every item from a user's cart, e.g. after their order has been placed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart_items WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return {"success": True}


def get_seller_cart_count(seller_id):
    """Returns the total number of units of a seller's products currently sitting in all buyer carts."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(c.quantity)
        FROM cart_items c
        JOIN products p ON c.product_id = p.product_id
        WHERE p.seller_id = ?
    ''', (seller_id,))
    result = cursor.fetchone()[0]
    conn.close()
    return result or 0


# Messaging functions
def has_conversation(user_id, other_id):
    """Returns True if the two users have ever exchanged a message (in either direction).
    Messages one user deleted still count, since the other user may still have their copy."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1 FROM messages
        WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?)
        LIMIT 1
    ''', (user_id, other_id, other_id, user_id))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def can_message(sender_id, recipient_id):
    """Checks whether sender_id may send a message to recipient_id.
    - Buyers can start a conversation with any seller, with or without an order.
    - Sellers can only start a conversation with a buyer who has ordered one of their products.
    - Once a conversation exists (started by either side), both users can keep messaging indefinitely.
    Returns {"allowed": bool, "message": reason it isn't allowed}."""
    if sender_id < 1:
        return {"allowed": False, "message": "Please log in to send messages."}
    if sender_id == recipient_id:
        return {"allowed": False, "message": "You can't send a message to yourself."}

    recipient = get_user(recipient_id) if recipient_id >= 1 else None
    if recipient is None:
        return {"allowed": False, "message": "That user doesn't exist."}

    sender = get_user(sender_id)
    sender_role = sender["role"] if sender else None
    if (sender_role == "seller" and recipient["role"] == "buyer"
            and not has_conversation(sender_id, recipient_id)
            and not has_ordered_from_seller(recipient_id, sender_id)):
        return {"allowed": False,
                "message": f"You can only start a conversation with a buyer who has ordered from you. "
                           f"{recipient['username']} hasn't placed an order with you yet."}

    return {"allowed": True, "message": ""}


def send_message(sender_id, recipient_id, subject, body):
    """Sends an email-style message from one user to another.
    Sending the first message adds each user to the other's conversation list."""
    subject = (subject or "").strip()
    body = (body or "").strip()

    permission = can_message(sender_id, recipient_id)
    if not permission["allowed"]:
        return {"success": False, "message": permission["message"]}
    if not subject:
        return {"success": False, "message": "Please enter a subject."}
    if not body:
        return {"success": False, "message": "Please enter a message."}
    if is_blocked(sender_id, recipient_id):
        return {"success": False,
                "message": f"You've blocked {get_user(recipient_id)['username']}. Unblock them to send a message."}

    # If the recipient has blocked the sender, the message is still saved (so unblocking can reveal it),
    # but it's stored as already read so it never notifies the recipient. The sender isn't told.
    already_read = 1 if is_blocked(recipient_id, sender_id) else 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (sender_id, recipient_id, subject, body, is_read)
        VALUES (?, ?, ?, ?, ?)
    ''', (sender_id, recipient_id, subject, body, already_read))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Message sent."}


def list_conversations(user_id):
    """Returns every user this user has messaged with, most recent conversation first.
    Each entry has the other user's ID, the latest message's subject and time, and the unread count."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END AS other_id,
            MAX(message_id) AS last_message_id,
            SUM(CASE WHEN recipient_id = ? AND is_read = 0 THEN 1 ELSE 0 END) AS unread
        FROM messages
        WHERE (sender_id = ? AND sender_deleted = 0) OR (recipient_id = ? AND recipient_deleted = 0)
        GROUP BY other_id
        HAVING other_id NOT IN (SELECT blocked_id FROM blocked_users WHERE blocker_id = ?)
        ORDER BY last_message_id DESC
    ''', (user_id, user_id, user_id, user_id, user_id))
    rows = cursor.fetchall()

    conversations = []
    for other_id, last_message_id, unread in rows:
        cursor.execute('SELECT subject, sent_at FROM messages WHERE message_id = ?', (last_message_id,))
        subject, sent_at = cursor.fetchone()
        cursor.execute('SELECT username FROM accounts WHERE user_id = ?', (other_id,))
        account = cursor.fetchone()
        conversations.append({"user_id": other_id, "username": account[0] if account else None,
                              "last_subject": subject, "last_sent_at": sent_at, "unread": unread})
    conn.close()
    return conversations


def get_conversation(user_id, other_id):
    """Returns all messages between two users, oldest first, and marks the ones sent to user_id as read."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT message_id, sender_id, recipient_id, subject, body, sent_at
        FROM messages
        WHERE (sender_id = ? AND recipient_id = ? AND sender_deleted = 0)
           OR (sender_id = ? AND recipient_id = ? AND recipient_deleted = 0)
        ORDER BY message_id
    ''', (user_id, other_id, other_id, user_id))
    rows = cursor.fetchall()

    cursor.execute('''
        UPDATE messages SET is_read = 1
        WHERE sender_id = ? AND recipient_id = ? AND is_read = 0 AND recipient_deleted = 0
    ''', (other_id, user_id))
    conn.commit()
    conn.close()

    return [
        {"id": r[0], "sender_id": r[1], "recipient_id": r[2], "subject": r[3],
         "body": r[4], "sent_at": r[5], "sent_by_me": r[1] == user_id}
        for r in rows
    ]


def block_user(blocker_id, blocked_id):
    """Blocks another user's communication. Their messages are hidden from the blocker until unblocked."""
    if blocker_id == blocked_id or blocked_id < 1:
        return {"success": False, "message": "You can't block that user."}
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO blocked_users (blocker_id, blocked_id) VALUES (?, ?)',
                   (blocker_id, blocked_id))
    conn.commit()
    conn.close()
    blocked = get_user(blocked_id)
    return {"success": True, "message": f"{blocked['username'] if blocked else 'That user'} has been blocked."}


def unblock_user(blocker_id, blocked_id):
    """Unblocks a user, revealing their hidden communication again."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM blocked_users WHERE blocker_id = ? AND blocked_id = ?', (blocker_id, blocked_id))
    conn.commit()
    conn.close()


def is_blocked(blocker_id, blocked_id):
    """Returns True if blocker_id has blocked blocked_id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM blocked_users WHERE blocker_id = ? AND blocked_id = ?', (blocker_id, blocked_id))
    blocked = cursor.fetchone() is not None
    conn.close()
    return blocked


def list_blocked_users(user_id):
    """Returns everyone this user has blocked, most recently blocked first."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.blocked_id, b.blocked_at, a.username FROM blocked_users b
        LEFT JOIN accounts a ON b.blocked_id = a.user_id
        WHERE b.blocker_id = ?
        ORDER BY b.blocked_at DESC, b.blocked_id DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": r[0], "blocked_at": r[1], "username": r[2]} for r in rows]


def _purge_deleted_messages(cursor):
    """Permanently removes messages that both the sender and the recipient have deleted."""
    cursor.execute('DELETE FROM messages WHERE sender_deleted = 1 AND recipient_deleted = 1')


def delete_message(user_id, message_id):
    """Deletes one message from this user's mailbox only; the other user keeps their copy, like email.
    Returns the other user's ID, or None if the message isn't in this user's mailbox."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sender_id, recipient_id FROM messages
        WHERE message_id = ?
          AND ((sender_id = ? AND sender_deleted = 0) OR (recipient_id = ? AND recipient_deleted = 0))
    ''', (message_id, user_id, user_id))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return None

    sender_id, recipient_id = row
    if sender_id == user_id:
        cursor.execute('UPDATE messages SET sender_deleted = 1 WHERE message_id = ?', (message_id,))
    else:
        cursor.execute('UPDATE messages SET recipient_deleted = 1 WHERE message_id = ?', (message_id,))
    _purge_deleted_messages(cursor)
    conn.commit()
    conn.close()
    return recipient_id if sender_id == user_id else sender_id


def delete_conversation(user_id, other_id):
    """Deletes every message between two users from this user's mailbox only."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE messages SET sender_deleted = 1 WHERE sender_id = ? AND recipient_id = ?',
                   (user_id, other_id))
    cursor.execute('UPDATE messages SET recipient_deleted = 1 WHERE sender_id = ? AND recipient_id = ?',
                   (other_id, user_id))
    _purge_deleted_messages(cursor)
    conn.commit()
    conn.close()






# Command Line Interface (for standalone testing)
def main():
    init_db()
    while True:
        print("\n=== Local Artisan Platform - CMD Prototype ===")
        print("1. View All Products")
        print("2. Add a Product")
        print("3. Remove a Product")
        print("4. View Products by Seller ID")
        print("5. Exit")

        choice = input("\nSelect an option (1-5): ").strip()

        if choice == '1':
            products = list_products()
            if not products:
                print("\n--- No products found in the database. ---")
            else:
                print("\n" + "=" * 60)
                print(f"{'ID':<5} | {'Seller':<8} | {'Title':<20} | {'Price':<8} | {'Stock':<6}")
                print("=" * 60)
                for p in products:
                    print(f"{p[0]:<5} | {p[1]:<8} | {p[2]:<20} | ${p[3]:<7.2f} | {p[4]:<6}")
                print("=" * 60)

        elif choice == '2':
            try:
                seller_id = int(input("Enter Seller ID: "))
                title = input("Enter Product Title: ")
                description = input("Enter Product Description: ")
                price = float(input("Enter Product Price ($): "))
                stock_quantity = int(input("Enter Stock Quantity: "))
                result = add_product(seller_id, title, description, price, stock_quantity)
                prefix = "[Success]" if result["success"] else "[Error]"
                print(f"\n{prefix}: {result['message']}")
            except ValueError:
                print("\n[Error]: Please enter valid numbers for Seller ID, Price, and Stock.")

        elif choice == '3':
            try:
                product_id = int(input("Enter Product ID to remove: "))
                result = remove_product(product_id)
                prefix = "[Success]" if result["success"] else "[Notice]"
                print(f"\n{prefix}: {result['message']}")
            except ValueError:
                print("\n[Error]: Please enter a valid Product ID number.")

        elif choice == '4':
            try:
                seller_id = int(input("Enter Seller ID to search for: "))
                products = list_products_by_seller(seller_id)
                if not products:
                    print(f"\n--- No products found for Seller ID {seller_id}. ---")
                else:
                    print("\n" + "=" * 70)
                    print(f"Products for Seller ID: {seller_id}")
                    print("=" * 70)
                    print(f"{'ID':<5} | {'Title':<20} | {'Price':<8} | {'Stock':<6} | {'Description'}")
                    print("-" * 70)
                    for p in products:
                        desc = p[2] if p[2] else ""
                        print(f"{p[0]:<5} | {p[1]:<20} | ${p[3]:<7.2f} | {p[4]:<6} | {desc}")
                    print("=" * 70)
            except ValueError:
                print("\n[Error]: Please enter a valid Seller ID number.")

        elif choice == '5':
            print("\nExiting prototype. Goodbye!")
            break
        else:
            print("\n[Error]: Invalid option. Please choose between 1 and 5.")


if __name__ == '__main__':
    main()