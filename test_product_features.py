#Bryan Bermudez- One-command checks for editing, deleting and searching products
"""Checks the seller edit, seller delete and keyword search features.

Run from the project folder:  python test_product_features.py
It uses a temporary database, so your real products are not touched.
"""
import os
import sqlite3
import tempfile

import database

# Point the app at a throwaway database BEFORE the app is imported
_tmp = tempfile.mkdtemp()
database.DB_PATH = os.path.join(_tmp, "test.db")
database.init_db()

import app as shop  # noqa: E402

shop.app.secret_key = "test-only"   # lets the test browser act as different sellers
client = shop.app.test_client()
results = []


def check(description, passed):
    results.append(passed)
    print(f"  {'PASS' if passed else 'FAIL'}  {description}")


def as_seller(seller_id):
    """Makes the test browser act as the given seller."""
    with client.session_transaction() as session:
        session["user_id"] = seller_id


def edit(pid, title="Big Mug", description="new text", price="14", stock="7"):
    return client.put(f"/api/products/{pid}", json={
        "title": title, "description": description, "price": price, "stock_quantity": stock})


def page(url):
    return client.get(url).get_data(as_text=True)


def titles_in_search(keyword):
    return [row[2] for row in shop.search_products(keyword)]


# Test products (seller 1 owns all of them; seller 2 owns one product too)
database.add_product(1, "Ceramic Mug", "blue glaze", 12.00, 5, ["ceramic"])
database.add_product(1, "Wool Scarf", "warm and handmade", 28.50, 3)
database.add_product(1, "Mug Rack", "holds a mug", 18.00, 2)
database.add_product(2, "Other Seller Item", "not yours", 5.00, 1)
ids = {row[2]: row[0] for row in database.list_products()}
as_seller(1)

print("\nSTORY 1: EDIT A PRODUCT")
mug = ids["Ceramic Mug"]
check("Seller can edit a product they own", edit(mug).status_code == 200)
saved = database.get_product(mug)
check("Title, description, price and stock are all saved",
      (saved["title"], saved["description"], saved["price"], saved["stock"]) == ("Big Mug", "new text", 14.0, 7))
shown = page(f"/product/{mug}")
check("The product page shows the new title, description and price",
      "Big Mug" in shown and "new text" in shown and "14.00" in shown)
check("An empty title is refused", edit(mug, title="").status_code == 400)
check("A price of 0 is refused", edit(mug, price="0").status_code == 400)
check("A negative stock is refused", edit(mug, stock="-1").status_code == 400)
check("A price that is not a number is refused", edit(mug, price="abc").status_code == 400)
check("Refused edits do not change the product", database.get_product(mug)["title"] == "Big Mug")
as_seller(2)
check("A different seller cannot edit it", edit(mug, title="Hacked").status_code == 404)
check("...and the product is unchanged", database.get_product(mug)["title"] == "Big Mug")
as_seller(1)
check("Editing a product that does not exist is refused", edit(9999).status_code == 404)

print("\nSTORY 2: DELETE A PRODUCT")
scarf = ids["Wool Scarf"]
con = sqlite3.connect(database.DB_PATH)
con.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (5, ?, 1)", (scarf,))
con.commit()
con.close()
as_seller(2)
check("A different seller cannot delete it", client.delete(f"/api/products/{scarf}").status_code == 404)
check("...and the product is still there", database.get_product(scarf) is not None)
as_seller(1)
check("Seller can delete a product they own", client.delete(f"/api/products/{scarf}").status_code == 200)
check("The deleted product is gone from the database", database.get_product(scarf) is None)
check("Its page now shows 404 (not found)", client.get(f"/product/{scarf}").status_code == 404)
check("It no longer appears in the product list", "Wool Scarf" not in page("/products"))
check("It was removed from buyers' carts", database.get_cart_items(5) == [])
check("Deleting it a second time is refused", client.delete(f"/api/products/{scarf}").status_code == 404)

print("\nSTORY 3: SEARCH BY KEYWORD")
database.add_product(1, "Wool Scarf", "warm and handmade", 28.50, 3)   # put the scarf back for searching
check("Searching a name finds it ('mug' finds Big Mug and Mug Rack)",
      set(titles_in_search("mug")) == {"Big Mug", "Mug Rack"})
check("Searching a word from the description finds it ('holds' finds Mug Rack)",
      titles_in_search("holds") == ["Mug Rack"])
check("Capital letters do not matter ('MUG' = 'mug')", set(titles_in_search("MUG")) == set(titles_in_search("mug")))
check("Several words must all match ('big mug' finds Big Mug only)", titles_in_search("big mug") == ["Big Mug"])
check("Words that never appear together find nothing ('mug scarf')", titles_in_search("mug scarf") == [])
check("A word that is nowhere finds nothing ('zzzz')", titles_in_search("zzzz") == [])
check("Symbols are safe ('%', '_' and an apostrophe find nothing)",
      titles_in_search("%") == [] and titles_in_search("_") == [] and titles_in_search("it's") == [])
check("An empty search lists every product", len(titles_in_search("   ")) == len(database.list_products()))
results_page = page("/products?search=mug")
check("The /products page shows only the matches", "Mug Rack" in results_page and "Wool Scarf" not in results_page)
check("The search box keeps what you typed", 'value="mug"' in results_page)
check("A search with no matches shows a message", 'No products match "zzzz"' in page("/products?search=zzzz"))

passed = sum(results)
print(f"\n{passed} of {len(results)} checks passed.")
print("Everything works." if passed == len(results) else "Something failed: read the FAIL lines above.")
