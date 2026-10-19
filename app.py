from flask import Flask, render_template

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


@app.route("/seller")
def seller():
    return render_template("seller.html")

@app.route("/messages")
def messages():
    return render_template("messages.html")

@app.route("/archive")
def archive():
    return render_template("archive.html")

if __name__ == "__main__":
    app.run(debug=True)