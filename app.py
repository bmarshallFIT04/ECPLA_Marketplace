import os

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

from database import (
    #Bryan Bermudez- Imported delete functions for removing saved info
    init_db, add_product, remove_product, get_product, list_products, list_products_by_seller,
    get_product_tags, set_product_tags,
    save_shipping_address, get_shipping_address, save_payment_info, get_payment_info,
    add_to_cart, get_cart_items, update_cart_quantity, remove_from_cart, get_seller_cart_count,
    delete_shipping_address, delete_payment_info,
    add_account, authenticate,
    is_blocked, get_conversation, list_conversations, list_blocked_users, send_message, delete_message, delete_conversation, block_user, unblock_user,
    get_orders, get_order_details
)

app = Flask(__name__)
# Needed so the session can remember which user is logged in. Set SECRET_KEY in real deployments.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret-key")
DEFAULT_ID: int = -1
DEFAULT_NAME: str = "SampleUser"
DEFAULT_ROLE: str = "seller"

# Makes the current user's ID available to every template (shown in the nav bar)
# Note: Currently does not update the username and role to the corresponding ID when changed.
@app.context_processor
def inject_current_user():
    return {
        "current_user_id": session.get('user_id', DEFAULT_ID),
        "current_username": session.get('username', DEFAULT_NAME),
        "current_role": session.get('role', DEFAULT_ROLE)
    }



# TEMPORARY: switch which user you are, until real login is built. Remove this route once login exists.
@app.route("/dev/login/<int:user_id>")
def dev_login(user_id):
    if user_id < 1:
        abort(400)
    session['user_id'] = user_id
    return redirect(request.referrer or url_for('messages'))


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        # Checks validity before inserting into accounts table
        result = add_account(username, password, role)
        success: bool = result["success"]
        message: str = result["message"]

        # Notify user of account creation success/failure:
        if success:
            return redirect("/login")
        else:
            # To-do: Incorporate message into website notification
            print(message) # state reason for failure
            return redirect("/register")


    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Checks if user exists, then checks password hashes
        result = authenticate(username, password)
        success: int = result["success"]
        message: str = result["message"]

        # Notify user of login success or failure
        if success:
            # To-do: Add user_id and other fields to session
            session["username"] = username
            session["user_id"] = success[0]
            session["role"] = success[1]
            return redirect("/")
        else:
            # To-do: Incorporate message into website notification
            print(message) # state reason for failure
            return redirect("/login")

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
    return render_template("product.html", product=product, user_id=session.get('user_id', DEFAULT_ID))



@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    user_id = session.get('user_id', DEFAULT_ID)

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
    order_ids = get_orders(session.get('user_id', -1))
    order_details = [get_order_details(order) for order in order_ids] if order_ids else None

    return render_template(
        "orders.html",
        orders=order_details
    )


#Bryan Bermudez- Account page now shows the buyer's saved shipping and payment info
@app.route("/account")
def account():
    user_id = session.get('user_id', DEFAULT_ID)
    return render_template(
        "account.html",
        shipping=get_shipping_address(user_id),
        payment=get_payment_info(user_id)
    )


#Bryan Bermudez- Edit (or add) saved shipping address from the Account page
@app.route("/account/shipping", methods=["POST"])
def account_save_shipping():
    user_id = session.get('user_id', DEFAULT_ID)
    save_shipping_address(user_id, request.form["name"], request.form["address"])
    return redirect("/account")


#Bryan Bermudez- Remove saved shipping address from the Account page
@app.route("/account/shipping/remove", methods=["POST"])
def account_remove_shipping():
    user_id = session.get('user_id', DEFAULT_ID)
    delete_shipping_address(user_id)
    return redirect("/account")


#Bryan Bermudez- Edit (or add) saved payment info from the Account page
@app.route("/account/payment", methods=["POST"])
def account_save_payment():
    user_id = session.get('user_id', DEFAULT_ID)
    save_payment_info(user_id, request.form["card"], request.form["expiration"])
    return redirect("/account")


#Bryan Bermudez- Remove saved payment info from the Account page
@app.route("/account/payment/remove", methods=["POST"])
def account_remove_payment():
    user_id = session.get('user_id', DEFAULT_ID)
    delete_payment_info(user_id)
    return redirect("/account")


@app.route("/seller")
def seller():
    seller_id = session.get('user_id', DEFAULT_ID)

    products = [
        {"id": p[0], "title": p[1], "price": p[3], "stock": p[4], "tags": get_product_tags(p[0])}
        for p in list_products_by_seller(seller_id)
    ]

    # Get total number of this seller's products sitting in active buyer carts
    total_in_carts = get_seller_cart_count(seller_id)

    return render_template("seller.html", products=products, total_in_carts=total_in_carts)


def render_messages(user_id, other_id=None, error=None, form=None, show_blocked=False):
    """Renders the messages page: the conversation list, plus one conversation, the compose form,
    or the Blocked Users list."""
    # A blocked user's messages stay hidden (and unread status untouched) until they're unblocked
    other_blocked = bool(other_id) and is_blocked(user_id, other_id)
    thread = get_conversation(user_id, other_id) if other_id and not other_blocked else None

    if form is None:
        # Pre-fill the compose form, e.g. from a product page's "Message Seller" button
        form = {"recipient_id": request.args.get("to", ""), "subject": request.args.get("subject", ""), "body": ""}
        # Replies default to "Re: <latest subject>", like email
        if thread:
            last_subject = thread[-1]["subject"]
            form["subject"] = last_subject if last_subject.startswith("Re: ") else f"Re: {last_subject}"

    return render_template(
        "messages.html",
        conversations=list_conversations(user_id),
        other_id=other_id,
        other_blocked=other_blocked,
        thread=thread,
        error=error,
        form=form,
        show_blocked=show_blocked,
        blocked_users=list_blocked_users(user_id)
    )


# Messages page: list of everyone the user has messaged with, and a form to start a new conversation
@app.route("/messages")
def messages():
    user_id = session.get('user_id', DEFAULT_ID)
    return render_messages(user_id)


# Past messages with one user, with a form to reply
@app.route("/messages/<int:other_id>")
def conversation(other_id):
    user_id = session.get('user_id', DEFAULT_ID)
    if other_id == user_id:
        return redirect(url_for('messages'))
    return render_messages(user_id, other_id)


@app.route("/messages/send", methods=["POST"])
def message_send():
    user_id = session.get('user_id', DEFAULT_ID)
    form = {
        "recipient_id": request.form.get("recipient_id", "").strip(),
        "subject": request.form.get("subject", ""),
        "body": request.form.get("body", "")
    }

    try:
        recipient_id = int(form["recipient_id"])
    except ValueError:
        return render_messages(user_id, error="Please enter a valid recipient user ID.", form=form), 400

    result = send_message(user_id, recipient_id, form["subject"], form["body"])
    if not result["success"]:
        # Re-show the same page with the error, keeping what the user typed
        other_id = recipient_id if recipient_id != user_id and recipient_id > 0 else None
        return render_messages(user_id, other_id, error=result["message"], form=form), 400

    return redirect(url_for('conversation', other_id=recipient_id))


# Deletes one message from the current user's mailbox (the other user still sees it)
@app.route("/messages/delete/<int:message_id>", methods=["POST"])
def message_delete(message_id):
    user_id = session.get('user_id', DEFAULT_ID)
    other_id = delete_message(user_id, message_id)
    if other_id is None:
        abort(404)
    return redirect(url_for('conversation', other_id=other_id))


# Deletes the whole conversation with one user from the current user's mailbox
@app.route("/messages/<int:other_id>/delete", methods=["POST"])
def conversation_delete(other_id):
    user_id = session.get('user_id', DEFAULT_ID)
    delete_conversation(user_id, other_id)
    return redirect(url_for('messages'))


# Blocked Users list, where the user can unblock people
@app.route("/messages/blocked")
def blocked_users():
    user_id = session.get('user_id', DEFAULT_ID)
    return render_messages(user_id, show_blocked=True)


# Blocks a user: their communication is hidden and their new messages don't notify
@app.route("/messages/<int:other_id>/block", methods=["POST"])
def user_block(other_id):
    user_id = session.get('user_id', DEFAULT_ID)
    result = block_user(user_id, other_id)
    if not result["success"]:
        abort(400)
    return redirect(url_for('messages'))


# Unblocks a user: reveals their hidden communication and removes them from the Blocked Users list
@app.route("/messages/<int:other_id>/unblock", methods=["POST"])
def user_unblock(other_id):
    user_id = session.get('user_id', DEFAULT_ID)
    unblock_user(user_id, other_id)
    # Go back to where the Unblock button was clicked (the Blocked Users list or the conversation)
    if request.form.get("next") == "blocked":
        return redirect(url_for('blocked_users'))
    return redirect(url_for('conversation', other_id=other_id))


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
    seller_id = session.get('user_id', DEFAULT_ID)

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
    seller_id = session.get('user_id', DEFAULT_ID)

    tags = request.get_json().get('tags', [])
    if not isinstance(tags, list):
        return jsonify({"success": False, "message": "Tags must be a list."}), 400

    result = set_product_tags(product_id, seller_id, tags)
    status_code = 200 if result["success"] else 404
    return jsonify(result), status_code

#Shopping cart - bryan bermudez
@app.route("/cart/add/<int:product_id>", methods=["POST"])
def cart_add(product_id):
    user_id = session.get('user_id', DEFAULT_ID)  # Fallback to user 1 for now
    try:
        qty = int(request.form.get('quantity', 1))
    except ValueError:
        qty = 1

    add_to_cart(user_id, product_id, qty)
    return redirect(url_for('cart'))


@app.route("/cart/update/<int:cart_item_id>", methods=["POST"])
def cart_update(cart_item_id):
    try:
        qty = int(request.form.get('quantity', 1))
        update_cart_quantity(cart_item_id, qty)
    except ValueError:
        pass
    return redirect(url_for('cart'))


@app.route("/cart/remove/<int:cart_item_id>", methods=["POST"])
def cart_remove(cart_item_id):
    remove_from_cart(cart_item_id)
    return redirect(url_for('cart'))


@app.route("/cart")
def cart():
    user_id = session.get('user_id', DEFAULT_ID)
    items = get_cart_items(user_id)
    total = sum(item['price'] * item['quantity'] for item in items)
    return render_template("cart.html", cart_items=items, total=total)




if __name__ == "__main__":
    init_db()
    app.run(debug=True)
