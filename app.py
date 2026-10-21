from flask import Flask, render_template, request, redirect, url_for, session, jsonify

from database import init_db, add_product, remove_product, list_products_by_seller
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
    return render_template("products.html")


@app.route("/product")
def product():
    return render_template("product.html")


@app.route("/cart")
def cart():
    return render_template("cart.html")


@app.route("/checkout")
def checkout():
    return render_template("checkout.html")


@app.route("/orders")
def orders():
    return render_template("orders.html")


@app.route("/account")
def account():
    return render_template("account.html")


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
        stock_quantity=stock_quantity
    )

    status_code = 200 if result["success"] else 400
    return jsonify(result), status_code







if __name__ == "__main__":
    init_db()
    app.run(debug=True)
