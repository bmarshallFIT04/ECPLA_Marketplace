from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

from database import (
    init_db, add_product, remove_product, get_product, list_products, list_products_by_seller,
    get_product_tags, set_product_tags,
    save_shipping_address, get_shipping_address, save_payment_info, get_payment_info
)
app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/products")
def products():
    # Shows every seller's products, not just the logged-in user's
    all_products = [
        {"id": p[0], "seller_id": p[1], "title": p[2], "price": p[3], "stock": p[4],
         "description": p[5], "tags": get_product_tags(p[0])}
        for p in list_products()
    ]
    return render_template("products.html", products=all_products)


@app.route("/product/<int:product_id>")
def product(product_id):
    product = get_product(product_id)
    if product is None:
        abort(404)
    return render_template("product.html", product=product)


@app.route("/cart")
def cart():
    return render_template("cart.html")


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    # Fallback to default User ID 1 (SampleUser) since auth isn't fully built yet
    user_id = session.get('user_id', 1)

    if request.method == "POST":
        # Only overwrite saved info when the buyer ticks "Save for future orders"
        if request.form.get("save_shipping"):
            save_shipping_address(user_id, request.form["name"], request.form["address"])
        if request.form.get("save_payment"):
            save_payment_info(user_id, request.form["card"], request.form["expiration"])

        # Order placement logic will be added later

        return redirect("/orders")

    return render_template(
        "checkout.html",
        shipping=get_shipping_address(user_id),
        payment=get_payment_info(user_id)
    )


@app.route("/orders")
def orders():
    return render_template("orders.html")


@app.route("/account")
def account():
    return render_template("account.html")


@app.route("/seller")
def seller():
    # Fallback to default Seller ID 1 (SampleUser) since auth isn't fully built yet
    seller_id = session.get('user_id', 1)

    products = [
        {"id": p[0], "title": p[1], "price": p[3], "stock": p[4], "tags": get_product_tags(p[0])}
        for p in list_products_by_seller(seller_id)
    ]
    return render_template("seller.html", products=products)


@app.route("/messages")
def messages():
    return render_template("messages.html")


@app.route("/archive")
def archive():
    return render_template("archive.html")


@app.route("/return", methods=["GET", "POST"])
def return_product():

    if request.method == "POST":
        reason = request.form["reason"]
        resolution = request.form["resolution"]
        shipping = request.form["shipping"]

        # Database logic will be added later

        return redirect("/orders")

    return render_template("return.html")


#Bryan Bermudez - Add product
@app.route('/api/add-product', methods=['POST'])
def handle_add_product():
    # Use session if available, but fallback to default Seller ID 1 (SampleUser) since auth isn't fully built yet
    seller_id = session.get('user_id', 1)

    data = request.get_json()
    title = data.get('title')
    description = data.get('description')

    try:
        price = float(data.get('price', 0))
        stock_quantity = int(data.get('stock_quantity', 0))
    except ValueError:
        return jsonify({"success": False, "message": "Invalid price or stock quantity format."}), 400

    # Calls your database.py function, saving the product linked to the seller's info
    result = add_product(
        seller_id=seller_id,
        title=title,
        description=description,
        price=price,
        stock_quantity=stock_quantity,
        tags=data.get('tags', [])
    )

    status_code = 200 if result["success"] else 400
    return jsonify(result), status_code


# Add, edit, or remove a product's tags by sending its full new list of tags
@app.route('/api/products/<int:product_id>/tags', methods=['POST'])
def handle_set_tags(product_id):
    # Fallback to default Seller ID 1 (SampleUser) since auth isn't fully built yet
    seller_id = session.get('user_id', 1)

    tags = request.get_json().get('tags', [])
    if not isinstance(tags, list):
        return jsonify({"success": False, "message": "Tags must be a list."}), 400

    result = set_product_tags(product_id, seller_id, tags)
    status_code = 200 if result["success"] else 404
    return jsonify(result), status_code


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
