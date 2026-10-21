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
    conn.commit()
    conn.close()


def add_product(seller_id, title, description, price, stock_quantity):
    """Adds a new product to the database with validation checks."""
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
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Product '{title}' added to the database!"}


def remove_product(product_id):
    """Removes a product from the database by its ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE product_id = ?', (product_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    if rows_affected > 0:
        return {"success": True, "message": f"Product ID {product_id} has been removed."}
    else:
        return {"success": False, "message": f"No product found with ID {product_id}."}


def list_products():
    """Lists all products currently in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT product_id, seller_id, title, price, stock_quantity FROM products')
    products = cursor.fetchall()
    conn.close()
    return products


def list_products_by_seller(seller_id):
    """Searches and lists products belonging to a specific seller ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT product_id, title, description, price, stock_quantity FROM products WHERE seller_id = ?',
                   (seller_id,))
    products = cursor.fetchall()
    conn.close()
    return products


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