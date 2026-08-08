import json
import os
import re
import time
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)

app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-only-key-change-in-production')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'ADMIN123')

# Uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm', '.ogg'}


def allowed_file(filename):
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            # remember where to return
            session['next_admin'] = request.path
            flash('Please sign in as admin to access that page.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'products.json')


def read_products():
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_products(products):
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2)


ORDERS_PATH = os.path.join(os.path.dirname(__file__), 'data', 'orders.json')
CALLING_CODES_PATH = os.path.join(os.path.dirname(__file__), 'data', 'calling_codes.json')


def read_orders():
    if not os.path.exists(ORDERS_PATH):
        return []
    with open(ORDERS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_orders(orders):
    with open(ORDERS_PATH, 'w', encoding='utf-8') as f:
        json.dump(orders, f, indent=2)


def read_calling_codes():
    if not os.path.exists(CALLING_CODES_PATH):
        return []
    with open(CALLING_CODES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_calling_codes(codes):
    with open(CALLING_CODES_PATH, 'w', encoding='utf-8') as f:
        json.dump(codes, f, indent=2)


def tokenize_text(text):
    tokens = re.findall(r"[a-z0-9]+", (text or '').lower())
    stopwords = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'product', 'best', 'new', 'sale', 'of', 'to', 'in', 'on', 'a', 'an'}
    return [token for token in tokens if token not in stopwords]


def expand_tokens(tokens):
    synonyms = {
        'warm': {'warm', 'cozy', 'insulated', 'fleece', 'heated'},
        'jacket': {'jacket', 'hoodie', 'coat', 'sweater', 'pullover'},
        'hoodie': {'hoodie', 'jacket', 'sweatshirt', 'pullover'},
        'shoe': {'shoe', 'sneaker', 'boot', 'slipper'},
        'phone': {'phone', 'mobile', 'smartphone'},
        'charger': {'charger', 'powerbank', 'adapter'},
        'case': {'case', 'cover', 'shell'},
        'screen': {'screen', 'glass', 'protector'},
    }
    expanded = set()
    for token in tokens:
        expanded.add(token)
        for key, values in synonyms.items():
            if token == key or token in values:
                expanded.update(values)
                expanded.add(key)
    return expanded


def score_product_match(query, product):
    query_tokens = tokenize_text(query)
    if not query_tokens:
        return 0
    product_text = f"{product.get('name', '')} {product.get('description', '')} {product.get('brand', '')}"
    product_tokens = tokenize_text(product_text)
    query_expanded = expand_tokens(query_tokens)
    product_expanded = expand_tokens(product_tokens)
    shared = query_expanded.intersection(product_expanded)
    score = len(shared) * 2
    for token in query_tokens:
        if token in product_tokens:
            score += 2
        if token in product_text.lower():
            score += 1
    return score


def find_matching_products(products, query, limit=8):
    query = (query or '').strip()
    if not query:
        return products[:limit]

    scored = []
    for product in products:
        score = score_product_match(query, product)
        if score > 0:
            scored.append((score, product))

    if not scored:
        lowered_query = query.lower()
        scored = [
            (0, product)
            for product in products
            if lowered_query in f"{product.get('name','')} {product.get('description','')} {product.get('brand','')}".lower()
        ]

    scored.sort(key=lambda item: (-item[0], item[1].get('name', '')))
    return [product for _, product in scored[:limit]]


def get_related_products(base_product, products, limit=4):
    def normalize(text):
        tokens = re.findall(r"\w+", (text or '').lower())
        stopwords = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'product', 'best', 'new', 'sale'}
        return {token for token in tokens if token not in stopwords}

    base_text = f"{base_product.get('name', '')} {base_product.get('description', '')}"
    base_tokens = normalize(base_text)
    base_price = float(base_product.get('price', 0) or 0)
    scored = []

    for product in products:
        if product.get('id') == base_product.get('id'):
            continue
        text = f"{product.get('name', '')} {product.get('description', '')}".lower()
        other_tokens = normalize(text)
        shared = base_tokens.intersection(other_tokens)
        score = len(shared)
        if base_product.get('name', '').lower() in text:
            score += 2
        if product.get('name', '').lower() in base_text.lower():
            score += 2
        price_diff = abs(float(product.get('price', 0) or 0) - base_price)
        if base_price and price_diff <= base_price * 0.2:
            score += 1
        scored.append((score, price_diff, product))

    if not any(score for score, _, _ in scored):
        scored = [(0, abs(float(p.get('price', 0) or 0) - base_price), p) for _, _, p in scored]

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [product for _, _, product in scored[:limit]]


def get_recommended_products(products, orders, current_product_id, limit=4):
    if not products or not orders or not current_product_id:
        return []

    product_lookup = {p.get('id'): p for p in products if p.get('id')}
    base_product = product_lookup.get(current_product_id)
    if not base_product:
        return []

    co_purchase_counts = {}
    for order in orders:
        item_ids = [item.get('id') for item in order.get('items', []) if item.get('id')]
        if current_product_id not in item_ids:
            continue
        for item_id in item_ids:
            if item_id == current_product_id:
                continue
            co_purchase_counts[item_id] = co_purchase_counts.get(item_id, 0) + 1

    if co_purchase_counts:
        scored = []
        for item_id, count in co_purchase_counts.items():
            product = product_lookup.get(item_id)
            if not product:
                continue
            score = count
            if product.get('brand') and base_product.get('brand') and product.get('brand') == base_product.get('brand'):
                score += 1
            price_diff = abs(float(product.get('price', 0) or 0) - float(base_product.get('price', 0) or 0))
            if price_diff <= float(base_product.get('price', 0) or 0) * 0.25:
                score += 0.5
            scored.append((score, product))
        scored.sort(key=lambda item: (-item[0], item[1].get('name', '')))
        return [product for _, product in scored[:limit]]

    return get_related_products(base_product, products, limit=limit)


def summarize_reviews(reviews):
    if not reviews:
        return 'No review summary yet. Add feedback to see a quick AI summary.'

    positive_keywords = {
        'comfort': 'comfort',
        'warm': 'warmth',
        'soft': 'softness',
        'great': 'overall quality',
        'love': 'customer delight',
        'fast': 'fast delivery',
        'durable': 'durability',
        'easy': 'ease of use',
        'quality': 'quality',
        'color': 'style',
    }
    negative_keywords = {
        'slow': 'delivery speed',
        'small': 'sizing',
        'bad': 'quality issues',
        'late': 'delivery delays',
        'cold': 'warmth',
        'issue': 'issues',
        'problem': 'problems',
        'damage': 'damage concerns',
        'cheap': 'value concerns',
    }

    pros = []
    cons = []
    for review in reviews:
        feedback = (review.get('feedback') or '').lower()
        for keyword, label in positive_keywords.items():
            if keyword in feedback and label not in pros:
                pros.append(label)
        for keyword, label in negative_keywords.items():
            if keyword in feedback and label not in cons:
                cons.append(label)

    pros_text = ', '.join(pros[:3]) if pros else 'solid overall sentiment'
    cons_text = ', '.join(cons[:3]) if cons else 'a few minor concerns'
    return f"Pros: {pros_text}. Cons: {cons_text}."


def analyze_order_anomalies(orders):
    if not orders:
        return []

    total_values = [float(order.get('total', 0) or 0) for order in orders if order.get('total') is not None]
    avg_total = sum(total_values) / len(total_values) if total_values else 0
    anomalies = []

    for order in orders:
        reasons = []
        total = float(order.get('total', 0) or 0)
        if avg_total and total > avg_total * 2.5:
            reasons.append('high-value basket')
        if len(order.get('items', [])) >= 3 and total >= 100:
            reasons.append('bulk purchase pattern')
        if not str(order.get('address', '')).strip():
            reasons.append('missing address')
        feedback = (order.get('feedback') or '').lower()
        rating = order.get('rating')
        if rating is not None:
            if rating >= 4 and any(word in feedback for word in ['slow', 'late', 'bad', 'small', 'problem', 'damage']):
                reasons.append('review mismatch')
            if rating <= 2 and any(word in feedback for word in ['great', 'love', 'perfect', 'fast', 'excellent', 'good']):
                reasons.append('review mismatch')

        if reasons:
            anomalies.append({
                'order_id': order.get('id'),
                'phone': order.get('phone', 'Unknown'),
                'reasons': reasons,
                'severity': 'high' if len(reasons) >= 2 else 'medium',
            })

    return anomalies


def answer_support_question(question, products, orders, phone):
    q = (question or '').strip().lower()
    if not q:
        return 'Ask me about orders, returns, shipping, or product details.'

    if any(keyword in q for keyword in ['return', 'refund', 'exchange']):
        return 'Returns are available within 7 days for unused items with the original packaging. If you need help, I can guide you through the return steps.'

    if any(keyword in q for keyword in ['order', 'status', 'delivery', 'shipping', 'track']):
        if phone:
            customer_orders = [order for order in orders if order.get('phone') == phone]
            if customer_orders:
                latest = sorted(customer_orders, key=lambda o: o.get('created_at', ''), reverse=True)[0]
                return f"Your latest order {latest.get('id')} is currently {latest.get('status', 'pending')}."
        return 'I can help with order status. Please sign in to check your latest order or share an order ID.'

    matching_products = find_matching_products(products, q, limit=3)
    if matching_products:
        names = ', '.join(product.get('name', 'product') for product in matching_products)
        return f"I found products that match your request: {names}. I can also tell you about pricing, brand, or specs for any of them."

    if any(keyword in q for keyword in ['price', 'cost', 'cheap', 'expensive']):
        return 'Prices vary by product and brand. I can help compare a few items if you tell me the product names.'

    return 'I can answer questions about orders, returns, shipping, and product details. Try asking about a product name or your order status.'


# Helper functions for common operations
def calculate_cart_items(cart, products):
    """
    Calculate cart items and total from cart dict and products list.
    Returns tuple of (cart_items, total)
    """
    cart_items = []
    total = 0.0
    for product_id, quantity in cart.items():
        product = next((p for p in products if p['id'] == product_id), None)
        if product:
            item_total = product['price'] * quantity
            total += item_total
            cart_items.append({
                'id': product_id,
                'name': product['name'],
                'price': product['price'],
                'quantity': quantity,
                'total': item_total,
            })
    return cart_items, total


def get_product_ratings(product_id, orders):
    """
    Calculate average rating and rating count for a product from all orders.
    Returns tuple of (avg_rating, rating_count)
    """
    total_rating = 0
    rating_count = 0
    for order in orders:
        if order.get('rating') is None:
            continue
        for item in order.get('items', []):
            if item.get('id') == product_id:
                total_rating += order.get('rating', 0)
                rating_count += 1
    avg_rating = total_rating / rating_count if rating_count > 0 else 0
    return avg_rating, rating_count


def get_product_reviews(product_id, orders):
    """
    Get all reviews for a product from orders.
    Returns list of review dicts with rating, feedback, date, customer.
    """
    reviews = []
    for order in orders:
        if order.get('rating') is None:
            continue
        for item in order.get('items', []):
            if item.get('id') == product_id and order.get('feedback'):
                reviews.append({
                    'rating': order.get('rating'),
                    'feedback': order.get('feedback'),
                    'date': order.get('created_at', 'Recently'),
                    'customer': order.get('name', 'Anonymous')
                })
    return reviews


def validate_product_exists(product_id, products):
    """
    Find a product by ID. Returns product dict or None.
    """
    return next((p for p in products if p['id'] == product_id), None)


def validate_order_exists(order_id, orders):
    """
    Find an order by ID. Returns order dict or None.
    """
    return next((o for o in orders if o['id'] == order_id), None)


def validate_order_ownership(order, phone):
    """
    Check if an order belongs to the given phone number.
    Returns True if order matches phone or phone is None (admin context).
    """
    if phone is None:
        return True
    return order.get('phone') == phone


@app.route('/')
def index():
    products = read_products()
    orders = read_orders()

    search_query = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', '').strip()
    brand_filter = request.args.get('brand', '').strip()
    rating_filter = request.args.get('rating_filter', '').strip()

    brand_options = sorted({p.get('brand', '').strip() for p in products if p.get('brand')})

    ratings_by_product = {}
    rating_counts = {}
    for order in orders:
        if order.get('rating') is None:
            continue
        for item in order.get('items', []):
            pid = item.get('id')
            if not pid:
                continue
            ratings_by_product[pid] = ratings_by_product.get(pid, 0) + order['rating']
            rating_counts[pid] = rating_counts.get(pid, 0) + 1

    avg_rating = {}
    for pid, total_rating in ratings_by_product.items():
        avg_rating[pid] = total_rating / rating_counts.get(pid, 1)

    filtered_products = []
    for product in products:
        matches = True
        if search_query:
            text = f"{product.get('name','')} {product.get('description','')}".lower()
            if search_query.lower() not in text:
                matches = False
        if matches and brand_filter:
            if not product.get('brand') or product.get('brand', '').strip().lower() != brand_filter.lower():
                matches = False
        if matches and rating_filter:
            product_rating = avg_rating.get(product.get('id')) or 0
            if rating_filter == '5' and product_rating < 5:
                matches = False
            elif rating_filter == '4-5' and not (4 <= product_rating < 5):
                matches = False
            elif rating_filter == '3-4' and not (3 <= product_rating < 4):
                matches = False
            elif rating_filter == '2-3' and not (2 <= product_rating < 3):
                matches = False
            elif rating_filter == '1-2' and not (1 <= product_rating < 2):
                matches = False
        if matches:
            product['avg_rating'] = avg_rating.get(product.get('id'), 0)
            filtered_products.append(product)

    if sort_by == 'price_asc':
        filtered_products.sort(key=lambda p: p.get('price', 0))
    elif sort_by == 'price_desc':
        filtered_products.sort(key=lambda p: p.get('price', 0), reverse=True)

    cart = session.get('cart', {})
    cart_items, total = calculate_cart_items(cart, products)

    last_viewed_id = session.get('last_viewed_product_id')
    suggested_products = []
    if last_viewed_id:
        viewed_product = next((p for p in products if p['id'] == last_viewed_id), None)
        if viewed_product:
            suggested_products = get_recommended_products(products, orders, viewed_product['id'])

    ai_search_used = bool(search_query)
    if ai_search_used:
        filtered_products = find_matching_products(filtered_products, search_query, limit=len(filtered_products)) if filtered_products else []

    return render_template(
        'index.html',
        products=filtered_products,
        cart_items=cart_items,
        total=total,
        search_query=search_query,
        sort_by=sort_by,
        brand_filter=brand_filter,
        rating_filter=rating_filter,
        brands=brand_options,
        suggested_products=suggested_products,
        ai_search_used=ai_search_used,
    )


@app.route('/product/<product_id>')
def product_detail(product_id):
    products = read_products()
    product = validate_product_exists(product_id, products)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('index'))

    session['last_viewed_product_id'] = product_id
    related_products = get_related_products(product, products)
    
    # Get customer reviews and ratings for this product
    orders = read_orders()
    reviews = get_product_reviews(product_id, orders)
    avg_rating, rating_count = get_product_ratings(product_id, orders)
    
    review_summary = summarize_reviews(reviews)
    recommended_products = get_recommended_products(products, orders, product_id)
    
    # Get cart data
    cart = session.get('cart', {})
    cart_items, total = calculate_cart_items(cart, products)
    
    return render_template('product_detail.html', product=product, related_products=related_products, 
                         reviews=reviews, avg_rating=avg_rating, rating_count=rating_count,
                         review_summary=review_summary, recommended_products=recommended_products,
                         cart_items=cart_items, total=total)


@app.route('/support', methods=['GET', 'POST'])
def support():
    products = read_products()
    orders = read_orders()
    phone = session.get('phone')
    history = session.get('support_history', [])
    answer = None
    question = ''

    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        answer = answer_support_question(question, products, orders, phone)
        history.append({'question': question, 'answer': answer})
        session['support_history'] = history[-6:]

    return render_template('support.html', answer=answer, question=question, history=history, products=products)


@app.route('/admin')
@admin_required
def admin():
    # Admin dashboard with quick links and counts
    products = read_products()
    orders = read_orders()
    total_products = len(products)
    total_orders = len(orders)
    status_counts = {}
    for o in orders:
        st = o.get('status', 'pending')
        status_counts[st] = status_counts.get(st, 0) + 1
    unseen_count = sum(1 for o in orders if not o.get('seen'))
    anomalies = analyze_order_anomalies(orders)
    return render_template('admin.html', total_products=total_products, total_orders=total_orders, status_counts=status_counts, unseen_count=unseen_count, anomalies=anomalies)


@app.route('/admin/add', methods=['GET', 'POST'])
@admin_required
def admin_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand = request.form.get('brand', '').strip()
        price = request.form.get('price', '').strip()
        description = request.form.get('description', '').strip()
        image_url = request.form.get('image_url', '').strip()
        # primary image upload (device) - use uploaded file only if no image_url provided
        primary_file = request.files.get('primary_image')
        if (not image_url) and primary_file and getattr(primary_file, 'filename', ''):
            if allowed_file(primary_file.filename):
                fname = secure_filename(primary_file.filename)
                dest = os.path.join(UPLOAD_FOLDER, fname)
                primary_file.save(dest)
                image_url = '/static/uploads/' + fname
        # fallback placeholder
        if not image_url:
            image_url = 'https://via.placeholder.com/260x160?text=Product'
        # handle uploaded media files
        media_files = request.files.getlist('media_files')
        media_list = []
        for mf in media_files:
            if mf and mf.filename and allowed_file(mf.filename):
                filename = secure_filename(mf.filename)
                dest = os.path.join(UPLOAD_FOLDER, filename)
                mf.save(dest)
                media_list.append('/static/uploads/' + filename)

        # handle additional media urls
        media_urls_text = request.form.get('media_urls', '').strip()
        if media_urls_text:
            for line in media_urls_text.splitlines():
                url = line.strip()
                if url:
                    media_list.append(url)

        if not name or not price or not brand:
            flash('Name, brand, and price are required.', 'error')
            return redirect(url_for('admin_add'))

        try:
            price_value = float(price)
        except ValueError:
            flash('Price must be a valid number.', 'error')
            return redirect(url_for('admin_add'))

        products = read_products()
        product = {
            'id': str(int(time.time() * 1000)),
            'name': name,
            'brand': brand,
            'description': description,
            'price': price_value,
            'imageUrl': image_url,
            'media': media_list,
        }
        products.insert(0, product)
        write_products(products)
        flash('Product added successfully.', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin_add.html')


@app.route('/admin/products')
@admin_required
def admin_products():
    products = read_products()
    return render_template('admin_products.html', products=products)


@app.route('/admin/edit/<product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    products = read_products()
    product = validate_product_exists(product_id, products)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('admin_products'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand = request.form.get('brand', '').strip()
        price = request.form.get('price', '').strip()
        description = request.form.get('description', '').strip()
        image_url = request.form.get('image_url', '').strip()
        # primary image upload (device) - use uploaded file only if no image_url provided
        primary_file = request.files.get('primary_image')
        if (not image_url) and primary_file and getattr(primary_file, 'filename', ''):
            if allowed_file(primary_file.filename):
                fname = secure_filename(primary_file.filename)
                dest = os.path.join(UPLOAD_FOLDER, fname)
                primary_file.save(dest)
                image_url = '/static/uploads/' + fname
        # if still empty, keep existing product image
        if not image_url:
            image_url = product.get('imageUrl', '')
        # handle uploaded media files
        media_files = request.files.getlist('media_files')
        media_list = product.get('media', [])[:]
        for mf in media_files:
            if mf and mf.filename and allowed_file(mf.filename):
                filename = secure_filename(mf.filename)
                dest = os.path.join(UPLOAD_FOLDER, filename)
                mf.save(dest)
                media_list.append('/static/uploads/' + filename)

        # handle additional media urls
        media_urls_text = request.form.get('media_urls', '').strip()
        if media_urls_text:
            for line in media_urls_text.splitlines():
                url = line.strip()
                if url:
                    media_list.append(url)

        if not name or not price or not brand:
            flash('Name, brand, and price are required.', 'error')
            return redirect(url_for('edit_product', product_id=product_id))

        try:
            price_value = float(price)
        except ValueError:
            flash('Price must be a valid number.', 'error')
            return redirect(url_for('edit_product', product_id=product_id))

        # update product
        product['name'] = name
        product['brand'] = brand
        product['price'] = price_value
        product['description'] = description
        product['imageUrl'] = image_url
        product['media'] = media_list
        write_products(products)
        flash('Product updated successfully.', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin_edit.html', product=product)


@app.route('/admin/delete/<product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    products = read_products()
    new_products = [p for p in products if p['id'] != product_id]
    if len(new_products) == len(products):
        flash('Product not found.', 'error')
    else:
        write_products(new_products)
        flash('Product deleted.', 'success')
    return redirect(url_for('admin_products'))


@app.route('/admin/brands')
@admin_required
def admin_brands():
    products = read_products()
    return render_template('admin_brands.html', products=products)


@app.route('/admin/brands/update/<product_id>', methods=['POST'])
@admin_required
def update_product_brand(product_id):
    products = read_products()
    product = validate_product_exists(product_id, products)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('admin_brands'))

    brand = request.form.get('brand', '').strip()
    if not brand:
        flash('Brand is required.', 'error')
        return redirect(url_for('admin_brands'))

    product['brand'] = brand
    write_products(products)
    flash(f"Brand updated for {product.get('name', 'Product')}", 'success')
    return redirect(url_for('admin_brands'))


@app.route('/admin/codes')
@admin_required
def admin_calling_codes():
    codes = read_calling_codes()
    return render_template('admin_codes.html', codes=codes)


@app.route('/admin/codes/add', methods=['POST'])
@admin_required
def admin_add_calling_code():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    if not code or not name:
        flash('Code and name are required.', 'error')
        return redirect(url_for('admin_calling_codes'))

    codes = read_calling_codes()
    if any(c['code'] == code for c in codes):
        flash('This calling code already exists.', 'error')
        return redirect(url_for('admin_calling_codes'))

    codes.insert(0, {'code': code, 'name': name})
    write_calling_codes(codes)
    flash('Calling code added.', 'success')
    return redirect(url_for('admin_calling_codes'))


@app.route('/admin/codes/delete', methods=['POST'])
@admin_required
def admin_delete_calling_code():
    code = request.form.get('code', '').strip()
    codes = read_calling_codes()
    new_codes = [c for c in codes if c['code'] != code]
    write_calling_codes(new_codes)
    flash('Calling code deleted.', 'success')
    return redirect(url_for('admin_calling_codes'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            phone = request.form.get('phone', '')
            country_code = request.form.get('country_code', '').strip()
            if phone is None:
                phone = ''
            phone = phone.strip()
            if not phone:
                flash('Phone number is required.', 'error')
                return redirect(url_for('login'))

            cleaned = ''.join([c for c in phone if c.isdigit()])
            if len(cleaned) < 6:
                flash('Please enter a valid phone number.', 'error')
                return redirect(url_for('login'))

            # save phone and country code separately
            session['phone'] = cleaned
            session['country_code'] = country_code
            next_url = session.pop('next', None)
            flash('Logged in successfully.', 'success')
            return redirect(next_url or url_for('index'))
        except Exception as e:
            # log to console and show friendly message
            print('Login error:', e)
            flash('An unexpected error occurred during login. Please try again.', 'error')
            return redirect(url_for('login'))

    # GET: provide available calling codes
    codes = read_calling_codes()
    return render_template('login.html', codes=codes)


@app.route('/logout')
def logout():
    session.pop('phone', None)
    flash('Logged out.', 'success')
    return redirect(url_for('index'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('Admin signed in.', 'success')
            nxt = session.pop('next_admin', None)
            return redirect(nxt or url_for('admin'))
        else:
            flash('Invalid admin password.', 'error')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash('Admin signed out.', 'success')
    return redirect(url_for('index'))


@app.route('/cart/add/<product_id>')
def add_to_cart(product_id):
    products = read_products()
    product = validate_product_exists(product_id, products)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('index'))

    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + 1
    session['cart'] = cart
    flash(f"Added {product['name']} to cart.", 'success')
    return redirect(url_for('index'))


@app.route('/cart/remove/<product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    if product_id in cart:
        del cart[product_id]
        session['cart'] = cart
        flash('Item removed from cart.', 'success')
    return redirect(url_for('index'))


@app.route('/cart/increase/<product_id>')
def increase_cart(product_id):
    products = read_products()
    product = validate_product_exists(product_id, products)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('index'))

    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + 1
    session['cart'] = cart
    return redirect(request.referrer or url_for('index'))


@app.route('/cart/decrease/<product_id>')
def decrease_cart(product_id):
    cart = session.get('cart', {})
    if product_id in cart:
        if cart[product_id] > 1:
            cart[product_id] = cart[product_id] - 1
        else:
            del cart[product_id]
        session['cart'] = cart
    return redirect(request.referrer or url_for('index'))


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    phone = session.get('phone')
    if not phone:
        # Save where to return after login
        session['next'] = url_for('checkout')
        flash('Please login with your phone number before checking out.', 'error')
        return redirect(url_for('login'))

    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty.', 'error')
        return redirect(url_for('index'))

    products = read_products()
    items, total = calculate_cart_items(cart, products)

    if request.method == 'GET':
        # Show checkout form with address
        address = session.get('address', '')
        return render_template('checkout.html', cart_items=items, total=total, address=address)

    # POST: finalize order with address
    address = request.form.get('address', '').strip()
    if not address:
        flash('Please enter a delivery address.', 'error')
        return redirect(url_for('checkout'))

    # Save address in session for convenience
    session['address'] = address

    order = {
        'id': str(int(time.time() * 1000)),
        'phone': phone,
        'items': items,
        'total': total,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
        'status': 'pending',
        'address': address,
        'seen': False,
    }

    orders = read_orders()
    orders.insert(0, order)
    write_orders(orders)

    # clear cart
    session.pop('cart', None)

    flash('Thank you for your purchase! Your order has been placed.', 'success')
    return redirect(url_for('order_confirmation', order_id=order['id']))


@app.route('/order/<order_id>')
def order_confirmation(order_id):
    orders = read_orders()
    order = validate_order_exists(order_id, orders)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('index'))
    return render_template('confirmation.html', order=order)


@app.route('/my-orders')
def my_orders():
    phone = session.get('phone')
    if not phone:
        session['next'] = url_for('my_orders')
        flash('Please login to view your orders.', 'error')
        return redirect(url_for('login'))

    orders = [o for o in read_orders() if o.get('phone') == phone]
    orders = sorted(orders, key=lambda o: o.get('created_at', ''), reverse=True)
    return render_template('my_orders.html', orders=orders)


@app.route('/order/<order_id>/feedback', methods=['POST'])
def order_feedback(order_id):
    phone = session.get('phone')
    if not phone:
        session['next'] = url_for('order_confirmation', order_id=order_id)
        flash('Please login to submit feedback.', 'error')
        return redirect(url_for('login'))

    orders = read_orders()
    order = validate_order_exists(order_id, orders)
    if not order or not validate_order_ownership(order, phone):
        flash('Order not found or access denied.', 'error')
        return redirect(url_for('my_orders'))

    feedback = request.form.get('feedback', '').strip()
    rating = request.form.get('rating')
    try:
        rating_value = int(rating) if rating else None
    except ValueError:
        rating_value = None

    order['feedback'] = feedback
    order['rating'] = rating_value
    write_orders(orders)
    flash('Thank you for your feedback.', 'success')
    return redirect(url_for('my_orders'))


@app.route('/admin/orders')
@admin_required
def admin_orders():
    orders = read_orders()
    # compute summary counts
    total_orders = len(orders)
    status_counts = {}
    for o in orders:
        st = o.get('status', 'pending')
        status_counts[st] = status_counts.get(st, 0) + 1
    unseen_count = sum(1 for o in orders if not o.get('seen'))
    anomalies = analyze_order_anomalies(orders)
    # show newest first
    return render_template('admin_orders.html', orders=orders, total_orders=total_orders, status_counts=status_counts, unseen_count=unseen_count, anomalies=anomalies)


@app.route('/admin/order/<order_id>')
@admin_required
def admin_view_order(order_id):
    orders = read_orders()
    order = validate_order_exists(order_id, orders)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('admin_orders'))
    # mark as seen when an admin opens the order
    if not order.get('seen'):
        order['seen'] = True
        write_orders(orders)
    return render_template('admin_order.html', order=order)


@app.route('/admin/order/<order_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_order(order_id):
    orders = read_orders()
    order = validate_order_exists(order_id, orders)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('admin_orders'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        status = request.form.get('status', 'pending')

        if not phone:
            flash('Phone is required.', 'error')
            return redirect(url_for('admin_edit_order', order_id=order_id))

        order['phone'] = phone
        order['address'] = address
        order['status'] = status
        write_orders(orders)
        flash('Order updated successfully.', 'success')
        return redirect(url_for('admin_view_order', order_id=order_id))

    return render_template('admin_order_edit.html', order=order)


@app.route('/admin/order/<order_id>/status', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    new_status = request.form.get('status')
    if not new_status:
        flash('Status is required.', 'error')
        return redirect(url_for('admin_view_order', order_id=order_id))

    orders = read_orders()
    for o in orders:
        if o['id'] == order_id:
            o['status'] = new_status
            write_orders(orders)
            flash('Order status updated.', 'success')
            return redirect(url_for('admin_view_order', order_id=order_id))

    flash('Order not found.', 'error')
    return redirect(url_for('admin_orders'))


@app.route('/admin/order/<order_id>/delete', methods=['POST'])
@admin_required
def admin_delete_order(order_id):
    orders = read_orders()
    order = validate_order_exists(order_id, orders)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('admin_orders'))

    new_orders = [o for o in orders if o['id'] != order_id]
    write_orders(new_orders)
    flash('Order removed.', 'success')
    return redirect(url_for('admin_orders'))


if __name__ == '__main__':
    # Debug mode is enabled only if FLASK_ENV=development; otherwise use safe defaults
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', debug=debug_mode)
