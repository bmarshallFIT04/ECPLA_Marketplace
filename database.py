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

    # Initializes User Accounts database (one row per tag on a product)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            UNIQUE(user_id, username)
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

# To-do: Hash password
def password_hash(password: str) -> str:
    return ""

# To-do: Validate input with regexx
def validate_input(text: str) -> bool:
    return True

# To-do: Complete add_account()
def add_account(username, password, role):

    '''Input Validation Checks'''
    # Username
    if (len(username) < 3) or (len(username) > 64) :
        return {"success": False, "message": "Username must be between 3 and 64 characters."}
    elif not validate_input(username):
        return {"success": False, "message": f"An account for {username} already exists."}
    elif get_account(username):
        return {"success": False, "message": "The username given includes invalid characters."}

    # Password
    if (len(password) < 6) or (len(password) > 64) :
        return {"success": False, "message": "Password must be between 6 and 64 characters."}
    elif not validate_input(username):
        return {"success": False, "message": "The password given includes invalid characters."}

    # Role
    if (role != "buyer") and (role != "seller"):
        return {"success": False, "message": "Account type must be a Buyer or Seller."}

    # Save account record
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO accounts (username, password, role)
        VALUES (?, ?, ?)
    ''', (username, password, role))
    conn.commit()
    conn.close()

    return {"success": True, "message": f"User account {username} has been successfully created."}

# To-do
def remove_account():
    pass

# To-do:
def get_account(username: str):
    pass

# To-do
def get_account_detail(field: str):
    pass

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