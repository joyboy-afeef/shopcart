import importlib


shop = importlib.import_module('app')


def test_semantic_search_matches_related_terms():
    products = [
        {'id': '1', 'name': 'Cozy Hoodie', 'description': 'Soft fleece for cold mornings', 'price': 49.99},
        {'id': '2', 'name': 'Running Shoes', 'description': 'Lightweight sneakers', 'price': 89.99},
    ]

    matches = shop.find_matching_products(products, 'warm jacket')

    assert any(item['id'] == '1' for item in matches)


def test_recommendations_use_order_patterns():
    products = [
        {'id': '1', 'name': 'Phone Case', 'description': 'Protective case', 'price': 12.0},
        {'id': '2', 'name': 'Screen Protector', 'description': 'Glass protector', 'price': 8.0},
        {'id': '3', 'name': 'Wireless Charger', 'description': 'Fast charging', 'price': 20.0},
    ]
    orders = [
        {'id': 'o1', 'items': [{'id': '1'}, {'id': '2'}]},
        {'id': 'o2', 'items': [{'id': '1'}, {'id': '3'}]},
    ]

    recs = shop.get_recommended_products(products, orders, '1', limit=4)

    assert any(item['id'] == '2' for item in recs)
    assert any(item['id'] == '3' for item in recs)


def test_review_summary_extracts_pros_and_cons():
    reviews = [
        {'feedback': 'Great comfort and warm fit, love the color.', 'rating': 5},
        {'feedback': 'Delivery was slow and sizing felt small.', 'rating': 2},
    ]

    summary = shop.summarize_reviews(reviews)

    assert 'Pros' in summary
    assert 'Cons' in summary
    assert 'comfort' in summary.lower()
