import os
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort, flash

from database import (
    #Bryan Bermudez- Imported delete functions for removing saved info
    init_db, add_product, remove_product, get_product, list_products, list_products_by_seller,
    list_best_selling_products,
    get_product_tags, set_product_tags,
    save_shipping_address, get_shipping_address, save_payment_info, get_payment_info,
    list_shipping_addresses, update_shipping_address, set_default_shipping_address,
    list_payment_methods, set_default_payment, validate_card,
    add_to_cart, get_cart_items, update_cart_quantity, remove_from_cart, get_seller_cart_count, clear_cart,
    delete_shipping_address, delete_payment_info,
    add_account, authenticate, get_user, get_account,
    is_blocked, get_conversation, list_conversations, list_blocked_users, send_message, delete_message, delete_conversation, block_user, unblock_user,
    can_message,
    get_orders, get_order_details, add_order, list_seller_buyers,
    set_tracking_number, add_order_update, get_order_updates, list_seller_orders, get_seller_sales, ORDER_STATUSES,
    MAX_TRACKING_NUMBER_LENGTH, MAX_ORDER_NOTE_LENGTH,
    MIN_USERNAME_LENGTH, MAX_USERNAME_LENGTH, MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH
)
#Bryan Bermudez- Imported product edit, delete and search modules
from product_manage_db import search_products
from product_manage_routes import product_manage

app = Flask(__name__)
# Needed so the session can remember which user is logged in. Set SECRET_KEY in real deployments.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret-key")
#Bryan Bermudez- Edit and delete product routes
app.register_blueprint(product_manage)
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
        "current_role": session.get('role', DEFAULT_ROLE),
        # Only true for a logged-in seller account (logged-out visitors don't count as sellers)
        "is_seller": is_seller()
    }


def is_seller():
    """Returns True if the logged-in account is a seller. Uses the role saved at login, not DEFAULT_ROLE."""
    return session.get('role') == "seller"


def login_required(view):
    """Route decorator: sends logged-out visitors to the login page instead of using the placeholder user."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped



@app.route("/")
def home():
    # "Featured from Local Sellers": the 4 best-selling products across all sellers
    return render_template("index.html", featured=list_best_selling_products(4))


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
            # Re-show the form with the reason (e.g. username taken), keeping the username and role
            return render_register(error=message, username=username, role=role), 400

    return render_register()


def render_register(error=None, username="", role="buyer"):
    """Renders the Create Account page, showing the same length limits that add_account() enforces."""
    return render_template(
        "register.html",
        error=error, username=username, role=role,
        min_username=MIN_USERNAME_LENGTH, max_username=MAX_USERNAME_LENGTH,
        min_password=MIN_PASSWORD_LENGTH, max_password=MAX_PASSWORD_LENGTH
    )


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


# Logs the current user out by forgetting their user ID, username, and role
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/products")
def products():
    # Shows every seller's products, not just the logged-in user's
    #Bryan Bermudez- Search products by keyword
    search = request.args.get("search", "").strip()
    all_products = [
        {"id": p[0], "seller_id": p[1], "title": p[2], "price": p[3], "stock": p[4],
         "description": p[5], "tags": get_product_tags(p[0])}
        for p in search_products(search)
    ]
    return render_template("products.html", products=all_products, search=search)


@app.route("/product/<int:product_id>")
def product(product_id):
    product = get_product(product_id)
    if product is None:
        abort(404)
    return render_template("product.html", product=product, user_id=session.get('user_id', DEFAULT_ID))



def render_checkout(user_id, cart_items, form=None, error=None):
    """Renders checkout with the buyer's saved addresses and cards to choose from (default pre-selected).
    Guests share the placeholder user ID, so they never see or save saved info."""
    logged_in = 'user_id' in session
    addresses = list_shipping_addresses(user_id) if logged_in else []
    cards = list_payment_methods(user_id) if logged_in else []
    if form is None:
        form = {"shipping_choice": str(addresses[0]["id"]) if addresses else "new",
                "payment_choice": str(cards[0]["id"]) if cards else "new",
                "name": "", "address": "", "expiration": ""}
    return render_template(
        "checkout.html",
        addresses=addresses,
        cards=cards,
        logged_in=logged_in,
        form=form,
        error=error,
        items=cart_items,
        total_price=sum(item["price"] * item["quantity"] for item in cart_items)
    )


def parse_id(value):
    """Turns a form value into an int ID, or None if it isn't one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    user_id = session.get('user_id', DEFAULT_ID)
    cart_items = get_cart_items(user_id)

    if request.method == "POST":
        logged_in = 'user_id' in session
        # Card number and CVV are deliberately not kept in `form`, so they're never written back into the page
        form = {key: request.form.get(key, "").strip()
                for key in ("shipping_choice", "payment_choice", "name", "address", "expiration")}

        def fail(message):
            return render_checkout(user_id, cart_items, form=form, error=message), 400

        if not cart_items:
            return fail("Your cart is empty.")

        # Shipping: one of the buyer's saved addresses, or a new one typed in (also used if no choice was sent)
        if form["shipping_choice"] in ("", "new") or not logged_in:
            if not form["name"] or not form["address"]:
                return fail("Please enter a full name and shipping address.")
            ship_to = {"full_name": form["name"], "address": form["address"]}
            if logged_in and request.form.get("save_shipping"):
                save_shipping_address(user_id, form["name"], form["address"])
        else:
            shipping_id = parse_id(form["shipping_choice"])
            # Check the ID explicitly: get_shipping_address(user, None) would quietly return the default
            ship_to = get_shipping_address(user_id, shipping_id) if shipping_id is not None else None
            if ship_to is None:
                return fail("Please choose a shipping address.")

        # Payment: one of the buyer's saved cards, or a new one typed in. The CVV is always re-entered.
        if form["payment_choice"] in ("", "new") or not logged_in:
            card_number, card_error = validate_card(request.form.get("card", ""), form["expiration"])
            if card_error:
                return fail(card_error)
            if logged_in and request.form.get("save_payment"):
                save_payment_info(user_id, card_number, form["expiration"])
        elif parse_id(form["payment_choice"]) is None or \
                get_payment_info(user_id, parse_id(form["payment_choice"])) is None:
            return fail("Please choose a card.")

        # Process each product as its own order, shipped to the address the buyer chose
        for item in cart_items:
            add_order(user_id, item["product_id"], item["quantity"], ship_to)

        # The order has been placed, so empty the buyer's cart
        clear_cart(user_id)
        return redirect("/orders")

    return render_checkout(user_id, cart_items)


@app.route("/orders")
def orders():
    order_ids = get_orders(session.get('user_id', -1))

    # Contains list of dictionaries, each containing the attributes of the corresponding orders from order_ids.
    # Contains None if there are no orders
    order_details = [get_order_details(order) for order in order_ids] if order_ids else None

    return render_template(
        "orders.html",
        orders=order_details
    )


def get_viewable_order(order_id):
    """Returns (order, viewer_is_seller) if the logged-in user is the order's buyer or the product's seller.
    Anyone else gets a 404, so they can't tell which order IDs exist."""
    user_id = session.get('user_id')
    order = get_order_details(order_id)
    if order is None:
        abort(404)
    viewer_is_seller = is_seller() and order["seller_id"] == user_id
    if order["user_id"] != user_id and not viewer_is_seller:
        abort(404)
    return order, viewer_is_seller


def render_order_detail(order_id, error=None):
    order, viewer_is_seller = get_viewable_order(order_id)
    return render_template(
        "order_detail.html",
        order=order,
        updates=get_order_updates(order_id),
        viewer_is_seller=viewer_is_seller,
        statuses=ORDER_STATUSES,
        max_tracking=MAX_TRACKING_NUMBER_LENGTH,
        max_note=MAX_ORDER_NOTE_LENGTH,
        error=error
    )


# Order details: buyers see the tracking number and shipment updates; the seller can also edit them
@app.route("/orders/<int:order_id>")
def order_detail(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_order_detail(order_id)


# Seller enters (or changes) the shipping/tracking number on an order
@app.route("/orders/<int:order_id>/tracking", methods=["POST"])
def order_set_tracking(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    get_viewable_order(order_id)  # 404 for anyone who isn't the buyer or seller
    result = set_tracking_number(order_id, session['user_id'], request.form.get("tracking_number", ""))
    if not result["success"]:
        return render_order_detail(order_id, error=result["message"]), 400
    flash(result["message"])
    return redirect(url_for('order_detail', order_id=order_id))


# Seller posts a shipment status update, e.g. "Out for delivery"
@app.route("/orders/<int:order_id>/status", methods=["POST"])
def order_add_update(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    get_viewable_order(order_id)  # 404 for anyone who isn't the buyer or seller
    result = add_order_update(order_id, session['user_id'],
                              request.form.get("status", ""), request.form.get("note", ""))
    if not result["success"]:
        return render_order_detail(order_id, error=result["message"]), 400
    flash(result["message"])
    return redirect(url_for('order_detail', order_id=order_id))


#Bryan Bermudez- Account page now shows the buyer's saved shipping and payment info
@app.route("/account")
@login_required
def account():
    user_id = session['user_id']
    return render_template(
        "account.html",
        addresses=list_shipping_addresses(user_id),
        cards=list_payment_methods(user_id)
    )


def flash_result(result):
    """Shows a database result's message on the next page, styled as success or error."""
    flash(result["message"], "success" if result["success"] else "error")


#Bryan Bermudez- Add a saved shipping address from the Account page
@app.route("/account/shipping", methods=["POST"])
@login_required
def account_save_shipping():
    flash_result(save_shipping_address(session['user_id'], request.form.get("name"), request.form.get("address")))
    return redirect("/account")


# Edit one saved shipping address
@app.route("/account/shipping/<int:shipping_id>", methods=["POST"])
@login_required
def account_update_shipping(shipping_id):
    flash_result(update_shipping_address(session['user_id'], shipping_id,
                                         request.form.get("name"), request.form.get("address")))
    return redirect("/account")


#Bryan Bermudez- Remove one saved shipping address from the Account page
@app.route("/account/shipping/<int:shipping_id>/remove", methods=["POST"])
@login_required
def account_remove_shipping(shipping_id):
    if delete_shipping_address(session['user_id'], shipping_id):
        flash("Address removed.", "success")
    return redirect("/account")


# Make one saved shipping address the default for checkout
@app.route("/account/shipping/<int:shipping_id>/default", methods=["POST"])
@login_required
def account_default_shipping(shipping_id):
    if set_default_shipping_address(session['user_id'], shipping_id):
        flash("Default address updated.", "success")
    return redirect("/account")


#Bryan Bermudez- Add a saved card from the Account page
@app.route("/account/payment", methods=["POST"])
@login_required
def account_save_payment():
    flash_result(save_payment_info(session['user_id'], request.form.get("card"), request.form.get("expiration")))
    return redirect("/account")


#Bryan Bermudez- Remove one saved card from the Account page
@app.route("/account/payment/<int:payment_id>/remove", methods=["POST"])
@login_required
def account_remove_payment(payment_id):
    if delete_payment_info(session['user_id'], payment_id):
        flash("Card removed.", "success")
    return redirect("/account")


# Make one saved card the default for checkout
@app.route("/account/payment/<int:payment_id>/default", methods=["POST"])
@login_required
def account_default_payment(payment_id):
    if set_default_payment(session['user_id'], payment_id):
        flash("Default card updated.", "success")
    return redirect("/account")


@app.route("/seller")
def seller():
    # Seller dashboard is only for seller accounts: send logged-out visitors to log in, refuse buyers
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not is_seller():
        abort(403)

    seller_id = session.get('user_id', DEFAULT_ID)

    products = [
        {"id": p[0], "title": p[1], "description": p[2], "price": p[3], "stock": p[4], "tags": get_product_tags(p[0])}
        for p in list_products_by_seller(seller_id)
    ]

    # Get total number of this seller's products sitting in active buyer carts
    total_in_carts = get_seller_cart_count(seller_id)

    # Buyers who have ordered from this seller; the seller can start a conversation with any of them
    buyers = list_seller_buyers(seller_id)

    # Orders placed for this seller's products, so they can add tracking numbers and status updates
    seller_orders = list_seller_orders(seller_id)

    # Seller Analytics: revenue, units sold, and order count from real orders
    sales = get_seller_sales(seller_id)

    return render_template("seller.html", products=products, total_in_carts=total_in_carts, buyers=buyers,
                           seller_orders=seller_orders, sales=sales)


def render_messages(user_id, other_id=None, error=None, form=None, show_blocked=False):
    """Renders the messages page: the conversation list, plus one conversation, the compose form,
    or the Blocked Users list."""
    # A blocked user's messages stay hidden (and unread status untouched) until they're unblocked
    other_blocked = bool(other_id) and is_blocked(user_id, other_id)
    thread = get_conversation(user_id, other_id) if other_id and not other_blocked else None

    # Whether the user may send to this person (e.g. sellers can only start conversations with their buyers)
    permission = can_message(user_id, other_id) if other_id and not other_blocked else {"allowed": True, "message": ""}

    if form is None:
        # Pre-fill the compose form, e.g. from a "Message Seller" button (?to=<username>&subject=...)
        form = {"recipient": request.args.get("to", ""), "subject": request.args.get("subject", ""), "body": ""}
        # Replies default to "Re: <latest subject>", like email
        if thread:
            last_subject = thread[-1]["subject"]
            form["subject"] = last_subject if last_subject.startswith("Re: ") else f"Re: {last_subject}"

    return render_template(
        "messages.html",
        conversations=list_conversations(user_id),
        other_id=other_id,
        other_user=get_user(other_id) if other_id else None,
        other_blocked=other_blocked,
        can_send=permission["allowed"],
        cannot_send_reason=permission["message"],
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
        "recipient": request.form.get("recipient", "").strip(),
        "subject": request.form.get("subject", ""),
        "body": request.form.get("body", "")
    }

    # Messages are addressed by username; look up which account that is
    recipient = get_account(form["recipient"])
    if recipient is None:
        error = f"No account found with the username \"{form['recipient']}\"." if form["recipient"] \
            else "Please enter a recipient username."
        return render_messages(user_id, error=error, form=form), 400
    recipient_id = recipient["user_id"]

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
    if not is_seller():
        return jsonify({"success": False, "message": "Only seller accounts can add products."}), 403

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
    if not is_seller():
        return jsonify({"success": False, "message": "Only seller accounts can edit product tags."}), 403

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
