# ShopCart

A full-stack e-commerce web application built with Python and Flask. It provides a complete storefront experience — product browsing, search, cart, and checkout — alongside an admin dashboard for managing products, brands, and orders. Data is stored in lightweight JSON files, so the project runs out of the box with no database setup required.

## Features

### Storefront
- Product catalog with images, pricing, and descriptions
- Search with filtering by brand, price range, and customer ratings
- Product detail pages with related products and customer reviews
- Shopping cart with add, remove, and quantity adjustments
- Phone-number based customer login
- Checkout flow with order confirmation and delivery address
- Order history ("My Orders") with status tracking
- Support chatbot for order and product questions

### Admin Dashboard
- Separate secure admin login
- Product management — add, edit, delete products and upload images
- Brand and country-calling-code management
- Order management — view, update status, and delete orders
- Dashboard stats overview

### Design
- Responsive layout that works on mobile, tablet, and desktop
- Consistent spacing, typography, and color system
- Client- and server-side form validation

## Tech Stack

- **Backend:** Python 3.9+, Flask
- **Templates:** Jinja2
- **Frontend:** HTML5, CSS3 (Grid, Flexbox, CSS Variables)
- **Storage:** JSON files (`data/products.json`, `data/orders.json`, `data/calling_codes.json`)

## Project Structure

```
project/
├── app.py                   # Flask application, routes, and helper functions
├── requirements.txt         # Python dependencies
├── README.md
├── data/                    # JSON "database" files
│   ├── products.json        # Product catalog
│   ├── orders.json          # Customer orders
│   └── calling_codes.json   # Country calling codes
├── static/
│   ├── styles.css           # Responsive CSS
│   └── uploads/             # Uploaded product images
└── templates/                # Jinja2 HTML templates
    ├── base.html             # Base layout
    ├── index.html             # Product listing & search
    ├── product_detail.html    # Product details & reviews
    ├── checkout.html          # Cart review & checkout
    ├── confirmation.html      # Order confirmation
    ├── my_orders.html         # Customer order history
    ├── login.html             # Customer login
    ├── support.html           # Support chatbot
    └── admin*.html            # Admin dashboard & management pages
```

## Getting Started

### Prerequisites
- Python 3.9 or higher
- pip

### Installation & Setup

1. Clone the repository and move into the project folder:
   ```bash
   git clone https://github.com/<your-username>/shopcart.git
   cd shopcart
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:
   ```bash
   python app.py
   ```

4. Open in your browser:
   - Storefront: [http://localhost:5000](http://localhost:5000)
   - Admin login: [http://localhost:5000/admin/login](http://localhost:5000/admin/login)

No environment variables are required to get the app running locally — it ships with development defaults out of the box.

### Optional: Custom Admin Password & Secret Key

By default the app uses a built-in admin password and session secret for convenience. To override them (recommended if you deploy this anywhere beyond your own machine), set:

```bash
export ADMIN_PASSWORD="your-secure-password"
export FLASK_SECRET_KEY="a-long-random-string"
```

**On Windows (PowerShell):**
```powershell
$env:ADMIN_PASSWORD="your-secure-password"
$env:FLASK_SECRET_KEY="a-long-random-string"
```

## Routes

| Page | Route | Description |
|---|---|---|
| Storefront | `/` | Browse, search, and filter products |
| Product Details | `/product/<product_id>` | View product info and reviews |
| Support | `/support` | Chatbot for help |
| Customer Login | `/login` | Sign in with phone number |
| My Orders | `/my-orders` | View and track orders |
| Admin Login | `/admin/login` | Sign in to the admin dashboard |
| Admin Dashboard | `/admin` | Store stats and quick links |
| Manage Products | `/admin/products` | Add, edit, delete products |
| Manage Brands | `/admin/brands` | Assign brands to products |
| Manage Codes | `/admin/codes` | Manage country calling codes |
| Manage Orders | `/admin/orders` | View and manage customer orders |

## Deploying to Production

If you plan to host this beyond local development:

1. Set strong, unique values for `ADMIN_PASSWORD` and `FLASK_SECRET_KEY` (never reuse the local defaults).
2. Run behind a production WSGI server instead of Flask's built-in server:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```
3. Consider migrating from JSON files to a proper database (PostgreSQL, MongoDB) if the store will handle real traffic or orders.
4. Serve over HTTPS.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
