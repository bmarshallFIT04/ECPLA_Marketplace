//Bryan Bermudez- Edit and delete products from the seller page
// Seller product editing and deleting on the seller page.
// Works on the markup from templates/_product_manage.html and talks to product_manage_routes.py.
(function () {
    function updateCard(card, product) {
        card.querySelector('.p-title').textContent = product.title;
        card.querySelector('.p-price').textContent = `Price: $${product.price.toFixed(2)}`;
        card.querySelector('.p-stock').textContent = `Stock: ${product.stock}`;
    }

    async function saveEdit(form) {
        const card = form.closest('.product-card');
        const errorLine = form.querySelector('.edit-error');
        errorLine.hidden = true;

        const payload = {
            title: form.elements['title'].value,
            description: form.elements['description'].value,
            price: form.elements['price'].value,
            stock_quantity: form.elements['stock_quantity'].value
        };

        try {
            const response = await fetch(`/api/products/${form.dataset.productId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();

            if (result.success) {
                updateCard(card, result.product);
                form.hidden = true;
            } else {
                errorLine.textContent = result.message;
                errorLine.hidden = false;
            }
        } catch (error) {
            console.error('Error:', error);
            errorLine.textContent = 'An error occurred while connecting to the server.';
            errorLine.hidden = false;
        }
    }

    async function deleteProduct(button) {
        if (!confirm('Delete this product? Buyers will no longer be able to see it.')) {
            return;
        }
        try {
            const response = await fetch(`/api/products/${button.dataset.productId}`, { method: 'DELETE' });
            const result = await response.json();

            if (result.success) {
                const grid = button.closest('.product-grid');
                button.closest('.product-card').remove();
                if (!grid.querySelector('.product-card')) {
                    const empty = document.createElement('p');
                    empty.textContent = "You haven't added any products yet.";
                    grid.appendChild(empty);
                }
            } else {
                alert(result.message);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred while connecting to the server.');
        }
    }

    document.addEventListener('click', (e) => {
        const edit = e.target.closest('.edit-btn');
        if (edit) {
            edit.closest('.product-card').querySelector('.edit-form').hidden = false;
            return;
        }
        const cancel = e.target.closest('.edit-cancel');
        if (cancel) {
            cancel.closest('.edit-form').hidden = true;
            return;
        }
        const del = e.target.closest('.delete-btn');
        if (del) {
            deleteProduct(del);
        }
    });

    document.addEventListener('submit', (e) => {
        if (e.target.matches('.edit-form')) {
            e.preventDefault();
            saveEdit(e.target);
        }
    });
})();
