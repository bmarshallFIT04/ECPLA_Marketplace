#Bryan Bermudez- Adds test products for trying edit, delete and search
"""Adds three test products for seller 1 so the edit, delete and search features can be tried.

Run from the project folder:  python seed_test_products.py
Safe to run more than once: a product that already exists (same title) is skipped.
"""
import database

SELLER_ID = 1

TEST_PRODUCTS = [
    ("Ceramic Mug", "blue glaze", 12.00, 5, ["ceramic", "handmade"]),
    ("Wool Scarf", "warm and handmade", 28.50, 3, ["wool"]),
    ("Mug Rack", "holds a mug", 18.00, 2, ["wood"]),
]


def main():
    database.init_db()
    existing = {row[1] for row in database.list_products_by_seller(SELLER_ID)}
    for title, description, price, stock, tags in TEST_PRODUCTS:
        if title in existing:
            print(f"Skipped (already there): {title}")
            continue
        result = database.add_product(SELLER_ID, title, description, price, stock, tags)
        print(result["message"])


if __name__ == "__main__":
    main()
