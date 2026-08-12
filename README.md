# 🛒 Shoppy — Multivendor Ecommerce REST API

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Django](https://img.shields.io/badge/Django-4.2-green?logo=django)
![DRF](https://img.shields.io/badge/DRF-3.17-red?logo=django)
![MySQL](https://img.shields.io/badge/MySQL-8.0-blue?logo=mysql)
![Redis](https://img.shields.io/badge/Redis-7.4-red?logo=redis)
![JWT](https://img.shields.io/badge/Auth-JWT-orange)
![Tests](https://img.shields.io/badge/Tests-201%20passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

> A production-grade multivendor ecommerce backend built with Django REST Framework.  
> Designed and developed as a portfolio project to demonstrate real-world backend engineering skills.

---

## 📌 What is Shoppy?

Shoppy is a fully featured **multivendor ecommerce REST API** — the kind of backend that powers platforms like Flipkart or Amazon Marketplace. It supports three distinct user roles (customer, vendor, admin), each with their own isolated data, permissions, and capabilities.

Built from scratch with industry-standard practices — OTP-based authentication, JWT tokens, Redis rate limiting, Razorpay payment integration, Cloudinary image storage, and comprehensive test coverage across all modules.

---

## ✨ Key Features

### 🔐 Authentication & Security
- OTP-based login via email (no passwords required for customers)
- 3-layer rate limiting — IP-based (Redis), per-contact (DB), resend cooldown
- Brute force protection — max 5 OTP attempts before lockout
- JWT access + refresh tokens with token blacklisting on rotation
- Role-based access control — customer, vendor, admin
- Email + password login for admin accounts

### 🏪 Multivendor System
- Vendors register with business details and await admin approval
- Admin approves/rejects/suspends vendors via Django admin panel
- Complete data isolation — vendors only see their own products, orders, inventory
- Commission tracking per order item (rate snapshotted at order time)
- Vendor dashboard with revenue, payout, best-selling products, 7/30-day charts

### 📦 Product Management
- Categories with parent-child subcategory support
- Products with variants (Size, Color, Storage etc.) and dynamic attributes
- Multiple images per product with Cloudinary CDN storage
- Soft delete — products hidden from listings but data preserved for order history
- Public listing with search, filters (category, brand, price range), ordering, pagination

### 🛒 Cart
- Persistent cart for logged-in users (DB-backed)
- Session-based guest cart (no login required)
- Guest cart automatically merges into user cart on login
- Real-time stock validation on add and update

### 📋 Orders
- COD orders confirmed instantly, cart cleared immediately
- UPI/Card orders via Razorpay — server-side signature verification (never trust frontend)
- Stock deducted at order creation time (prevents overselling)
- Stock automatically restored on cancellation
- Order item snapshots — product name and price preserved even if product is later edited
- Full status history audit trail (pending → confirmed → shipped → delivered)

### ⭐ Reviews
- Only users with a delivered order can review a product (verified purchase)
- One review per user per product with edit and soft delete
- Helpful votes system (cannot vote on own review)
- Rating summary with star breakdown (5★ count, 4★ count etc.)

### 📊 Vendor Dashboard
- Total revenue, payout, platform commission breakdown
- This month vs all-time performance
- Low stock and out-of-stock alerts
- Order status breakdown
- Revenue chart data for last 7 and 30 days
- Top 5 best-selling products
- Last 5 recent orders

---

## 🏗️ System Architecture

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│                           API Layer (Django REST Framework)                   │
├─────────────┬─────────────┬────────────┬──────────────┬───────────────────────┤
│ Accounts    │ Products    │ Cart       │ Orders       │ Vendors               │
├─────────────┼─────────────┼────────────┼──────────────┼───────────────────────┤
│ OTP Auth    │ CRUD        │ Guest Cart │ COD          │ Registration          │
│ JWT Auth    │ Search      │ User Cart  │ Razorpay     │ Dashboard             │
│ Addresses   │ Filters     │            │ Tracking     │ Inventory             │
└─────────────┴─────────────┴────────────┴──────────────┴───────────────────────┘
                │                    │                       │
      ┌─────────┴────────┐  ┌────────┴────────┐   ┌──────────┴─────────┐
      │ MySQL            │  │ Cloudinary      │   │ Redis              │
      │ Main Database    │  │ Image Storage   │   │ Rate Limiting      │
      └──────────────────┘  └─────────────────┘   └────────────────────┘
```


## 🗂️ Module Breakdown


|   Module   | Endpoints | Description                                                  |
|------------|-----------|--------------------------------------------------------------|
| `accounts` |   10      | OTP auth, JWT login, address management                      |
| `products` |    4      | Public product browsing and search                           |
| `cart`     |    5      | Add/update/remove items, guest cart, merge on login          |
| `orders`   |    5      | Place orders, Razorpay integration, status tracking          |
| `reviews`  |    7      | Verified purchase reviews, helpful votes                     |
| `vendors`  |   27      | Registration, products, orders, inventory, dashboard         |
| `admin`    |   20      | Order,Review,Product CRUD, variants, images, search, filters |
|            |           |                                                              |
| **Total**  |  **78**   |                                                              |

---
Note:APIs count may vary

## 🔑 User Roles


Customer → browse products, manage cart, place orders, write reviews
Vendor → register shop, manage own products, view own orders, manage inventory
Admin → approve vendors, manage all products, update order statuses, moderate reviews


---
## 🧰 Tech Stack

| Category              | Technology                               |
|-----------------------|------------------------------------------|
| Language              | Python 3.11                              |
| Framework             | Django 4.2, Django REST Framework 3.17   |
| Database              | MySQL 9.6                                |
| Cache / Rate Limiting | Redis 7.4 via django-redis               |
| Authentication        | JWT via djangorestframework-simplejwt    |
| Image Storage         | Cloudinary via django-cloudinary-storage |
| Payments              | Razorpay (test mode)                     |
| API Documentation     | drf-spectacular (Swagger UI + Redoc)     |
| Email (dev)           | Mailtrap sandbox                         |
| CORS                  | django-cors-headers                      |
---

## 🚀 Local Setup

### Prerequisites
- Python 3.11+
- MySQL 8.0+
- Redis (install via `brew install redis` on Mac)
- A free [Cloudinary](https://cloudinary.com) account
- A free [Mailtrap](https://mailtrap.io) account (for email OTPs in dev)
- A free [Razorpay](https://razorpay.com) account (test mode keys)

---

### 1. Clone the repository

```bash
git clone https://github.com/bharaths002/shoppy.git
cd shoppy
```

### 2. Create and activate virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create MySQL database

```sql
CREATE DATABASE shoppy;
```

### 5. Create `.env` file

Create a `.env` file in the root directory (same level as `manage.py`):

```env
SECRET_KEY=your-django-secret-key-here

# Database
DB_NAME=shoppy
DB_USER=root
DB_PASSWORD=your-mysql-password
DB_HOST=127.0.0.1
DB_PORT=3306

# Cloudinary
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

# Mailtrap (email OTP in dev)
EMAIL_HOST_USER=your-mailtrap-username
EMAIL_HOST_PASSWORD=your-mailtrap-password

# Razorpay (test mode)
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your-razorpay-secret
```

### 6. Start Redis

```bash
brew services start redis     # Mac
sudo service redis start      # Linux
```

Verify Redis is running:
```bash
redis-cli ping
# Should return: PONG
```

### 7. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 8. Create admin superuser

```bash
python manage.py createsuperuser
```

### 9. Start the development server


python manage.py runserver


---

## 📖 API Documentation

Once the server is running, visit:
|               URL                  |                Description                        |              
|------------------------------------|---------------------------------------------------|
| `http://127.0.0.1:8000/api/docs/`  | Swagger UI — interactive, test endpoints directly |
| `http://127.0.0.1:8000/api/redoc/` | Redoc — clean read-only reference                 |
| `http://127.0.0.1:8000/admin/`     | Django admin panel                                |
---

### Authentication in Swagger
1. `POST /api/accounts/sendotp/` with your email → OTP sent to Mailtrap inbox
2. `POST /api/accounts/verifyotp/` with OTP → copy the `access` token
3. Click **Authorize** (top right) → paste `Bearer <your_access_token>`
4. All protected endpoints now work automatically

---

## 🧪 Running Tests

```bash
# Run all 201 tests
python manage.py test --verbosity=2

# Run by module
python manage.py test accounts --verbosity=2
python manage.py test products --verbosity=2
python manage.py test cart     --verbosity=2
python manage.py test orders   --verbosity=2
python manage.py test reviews  --verbosity=2
python manage.py test vendors  --verbosity=2
```

Expected output:

Ran 201 tests in ~16s
OK ✅

### Test coverage by module


|  Module  | Tests |             What's covered                            |
|----------|-------|-------------------------------------------------------|
| accounts |  28   | OTP flow, rate limiting, brute force, address CRUD    |
| products |  24   | Listing, search, filters, CRUD, permissions           |
| cart     |  35   | Add/update/remove, guest cart, stock validation       |
| orders   |  28   | COD, Razorpay mock, cancel, stock restore, admin.     |
| reviews  |  26   | Verified purchase, edit/delete, helpful votes.        |
| vendors  |  60   | Registration, products, inventory, orders, dashboard  |
---
Note: APIs count may vary 

## 📁 Project Structure

```text
shoppy/
├── accounts/          # User auth, OTP, addresses, vendor profiles
├── products/          # Products, categories, brands, variants, images
├── cart/              # Cart items, guest cart, merge logic
├── orders/            # Orders, payments, status history
├── reviews/           # Reviews, helpful votes
├── vendors/           # Vendor dashboard, products, inventory, orders
├── config/             # Django settings, root URLs
├── requirements.txt
├── .env                # Not committed — see setup above
└── manage.py
```

---


## 🔒 Security Highlights

- OTP generated with Python `secrets` module (cryptographically secure, not `random`)
- 3-layer rate limiting prevents OTP spam and brute force attacks
- JWT token blacklisting — old refresh tokens invalidated on rotation
- Razorpay signature verified server-side — payment success never trusted from frontend
- Vendor data isolation enforced at query level — vendors physically cannot query other vendors' data
- Soft deletes preserve referential integrity — old orders never break when products are "deleted"
- Commission rates snapshotted at order time — vendor rate changes don't affect past orders

---

## 💡 Design Decisions Worth Noting

**Why OTP instead of password for customers?**

Eliminates forgotten password flows, reduces support overhead, and matches how most Indian ecommerce apps work (Swiggy, Zepto, Blinkit all use OTP login).

**Why reuse the same authentication flow?**
The same OTP + JWT authentication logic is reused across customers and vendors to avoid duplicating authentication code. Vendors additionally require **admin approval** before they can log in and access vendor features. Admin authentication uses Django's built-in **superuser** system.

**Why soft delete products?**
Hard deleting a product would break existing orders, cart items, and reviews that reference it. Soft delete keeps data integrity intact while hiding the product from customers.

**Why snapshot product data in OrderItem?**
If a vendor changes a product's name or price after a customer has ordered, the order must still show what the customer actually saw and paid. Snapshot fields (`product_name`, `unit_price`) ensure this.

**Why deduct stock at order creation not payment?**
Deducting at payment time (after Razorpay callback) creates a window where two customers can both "successfully" checkout the last unit. Deducting at order creation prevents overselling.

**Why vendor commission snapshotted per OrderItem?**
Admin might change a vendor's commission rate in the future. Past orders should reflect the commission that was in effect at the time — not the current rate.

---

## 🗺️ Roadmap (planned features)

- [ ] Celery + Celery Beat for async email delivery and scheduled tasks
- [ ] SMS OTP via Twilio or MSG91
- [ ] Elasticsearch for advanced product search
- [ ] Vendor payout management and bank transfer tracking
- [ ] Push notifications for order status updates
- [ ] Product import via CSV bulk upload
- [ ] Discount coupon system
- [ ] Wishlist

---

## 👨‍💻 Author

**Bharath S**  
Software Associate Engineer — Full Stack Developer  
📧 bharaths0218@gmail.com  
🔗 [GitHub](https://github.com/bharaths002)  
🔗 [LinkedIn](https://www.linkedin.com/in/bharaths18/)

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE) file for details.
