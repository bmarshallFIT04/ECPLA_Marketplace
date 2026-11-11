#Bryan Bermudez- Edit, delete and search functions for products
"""Database functions for managing and searching products.

Kept separate from database.py so the edit, delete and search features can change on their own.
Each function opens its own connection and uses database.DB_PATH, like the rest of the project.
"""
import sqlite3

import database


def update_product(product_id, seller_id, title, description, price, stock_quantity):
    """Updates a product's title, description, price and stock. Only the seller who owns it can change it."""
    title = (title or "").strip()
    if not title:
        return {"success": False, "message": "Title cannot be empty."}
    if price < 0.01:
        return {"success": False, "message": "Price must be at least $0.01 (cannot be negative or zero)."}
    if stock_quantity < 0:
        return {"success": False, "message": "Stock quantity cannot be negative."}

    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE products
        SET title = ?, description = ?, price = ?, stock_quantity = ?
        WHERE product_id = ? AND seller_id = ?
    ''', (title, description, price, stock_quantity, product_id, seller_id))
    conn.commit()
    updated = cursor.rowcount
    conn.close()

    if updated == 0:
        return {"success": False, "not_found": True,
                "message": f"No product found with ID {product_id} for this seller."}
    return {"success": True, "message": f"Product '{title}' updated.",
            "product": {"id": product_id, "title": title, "description": description,
                        "price": price, "stock": stock_quantity}}


def delete_owned_product(product_id, seller_id):
    """Deletes a product the seller owns, along with its tags, cart entries and reviews."""
    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE product_id = ? AND seller_id = ?', (product_id, seller_id))
    deleted = cursor.rowcount

    if deleted > 0:
        cursor.execute('DELETE FROM product_tags WHERE product_id = ?', (product_id,))
        cursor.execute('DELETE FROM cart_items WHERE product_id = ?', (product_id,))
        cursor.execute('DELETE FROM reviews WHERE product_id = ?', (product_id,))
    conn.commit()
    conn.close()

    if deleted == 0:
        return {"success": False, "message": f"No product found with ID {product_id} for this seller."}
    return {"success": True, "message": f"Product ID {product_id} has been removed."}


def search_products(keyword):
    """Finds products whose title or description contains every word in the keyword (case-insensitive).
    A blank keyword returns every product. Rows have the same columns as database.list_products()."""
    words = (keyword or "").split()
    if not words:
        return database.list_products()

    clauses = []
    params = []
    for word in words:
        escaped = word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        clauses.append("(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
        params.extend([f"%{escaped}%", f"%{escaped}%"])

    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f'''
        SELECT product_id, seller_id, title, price, stock_quantity, description
        FROM products
        WHERE {" AND ".join(clauses)}
        ORDER BY product_id DESC
    ''', params)
    products = cursor.fetchall()
    conn.close()
    return products
