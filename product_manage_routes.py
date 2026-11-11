#Bryan Bermudez- Routes for editing and deleting a seller's own products
"""Routes for editing and deleting a seller's own products.

A Flask Blueprint, so app.py only has to register it. The database work is in product_manage_db.py.
"""
from flask import Blueprint, jsonify, request, session

from product_manage_db import update_product, delete_owned_product

product_manage = Blueprint("product_manage", __name__)


def seller_only_error():
    """Returns an error response unless a seller account is logged in, otherwise None."""
    if 'user_id' not in session or session.get('role') != "seller":
        return jsonify({"success": False, "message": "Only seller accounts can change products."}), 403
    return None


def current_seller_id():
    return session['user_id']


# Edit an existing product's title, description, price and stock (only the seller who owns it)
@product_manage.route('/api/products/<int:product_id>', methods=['PUT'])
def handle_update_product(product_id):
    denied = seller_only_error()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        price = float(data.get('price', 0))
        stock_quantity = int(data.get('stock_quantity', 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid price or stock quantity format."}), 400

    result = update_product(
        product_id=product_id,
        seller_id=current_seller_id(),
        title=data.get('title'),
        description=data.get('description'),
        price=price,
        stock_quantity=stock_quantity
    )

    if result["success"]:
        return jsonify(result), 200
    return jsonify(result), 404 if result.get("not_found") else 400


# Delete a product the logged-in seller owns, so it is no longer available to buyers
@product_manage.route('/api/products/<int:product_id>', methods=['DELETE'])
def handle_delete_product(product_id):
    denied = seller_only_error()
    if denied:
        return denied
    result = delete_owned_product(product_id, current_seller_id())
    return jsonify(result), 200 if result["success"] else 404
