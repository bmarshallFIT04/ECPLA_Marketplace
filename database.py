import sqlite3
import os

# Set database path inside the project's 'instance' directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'marketplace.db')


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

    # Initializes saved checkout information (one saved address and card per user)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_shipping (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            address TEXT NOT NULL
        )
    ''')

    # The CVV is intentionally never stored; buyers re-enter it for each order
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_payment (
            user_id INTEGER PRIMARY KEY,
            card_number TEXT NOT NULL,
            expiration TEXT NOT NULL
        )
    ''')

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


def get_product(product_id):
    """Returns one product (with its tags) as a dict, or None if no product has that ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT product_id, seller_id, title, description, price, stock_quantity
        FROM products
        WHERE product_id = ?
    ''', (product_id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None
    return {"id": row[0], "seller_id": row[1], "title": row[2], "description": row[3],
            "price": row[4], "stock": row[5], "tags": get_product_tags(row[0])}


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


def save_shipping_address(user_id, full_name, address):
    """Saves a user's shipping address for future orders, replacing any previously saved one."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO saved_shipping (user_id, full_name, address) VALUES (?, ?, ?)',
                   (user_id, full_name, address))
    conn.commit()
    conn.close()


def get_shipping_address(user_id):
    """Returns a user's saved shipping address as a dict, or None if they haven't saved one."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT full_name, address FROM saved_shipping WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return {"full_name": row[0], "address": row[1]} if row else None


#Bryan Bermudez- Remove a buyer's saved shipping address
def delete_shipping_address(user_id):
    """Removes a user's saved shipping address."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM saved_shipping WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def save_payment_info(user_id, card_number, expiration):
    """Saves a user's card for future orders, replacing any previously saved one. The CVV is never saved."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO saved_payment (user_id, card_number, expiration) VALUES (?, ?, ?)',
                   (user_id, card_number, expiration))
    conn.commit()
    conn.close()


def get_payment_info(user_id):
    """Returns a user's saved card as a dict, or None if they haven't saved one."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT card_number, expiration FROM saved_payment WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return {"card_number": row[0], "expiration": row[1]} if row else None


#Bryan Bermudez- Remove a buyer's saved payment information
def delete_payment_info(user_id):
    """Removes a user's saved card."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM saved_payment WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

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
def send_message(sender_id, recipient_id, subject, body):
    """Sends an email-style message from one user to another."""
    subject = (subject or "").strip()
    body = (body or "").strip()

    if sender_id == recipient_id:
        return {"success": False, "message": "You can't send a message to yourself."}
    if recipient_id < 1:
        return {"success": False, "message": "Please enter a valid recipient user ID."}
    if not subject:
        return {"success": False, "message": "Please enter a subject."}
    if not body:
        return {"success": False, "message": "Please enter a message."}
    if is_blocked(sender_id, recipient_id):
        return {"success": False, "message": f"You've blocked User #{recipient_id}. Unblock them to send a message."}

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
        conversations.append({"user_id": other_id, "last_subject": subject,
                              "last_sent_at": sent_at, "unread": unread})
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
    return {"success": True, "message": f"User #{blocked_id} has been blocked."}


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
        SELECT blocked_id, blocked_at FROM blocked_users
        WHERE blocker_id = ?
        ORDER BY blocked_at DESC, blocked_id DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": r[0], "blocked_at": r[1]} for r in rows]


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