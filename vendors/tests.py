from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from accounts.models import VendorProfile, OTP
from products.models import (
    Product, Category, Brand,
    ProductVariant, AttributeType, VariantAttribute
)
from orders.models import Order, OrderItem
from accounts.models import Address
from cart.models import Cart, CartItem

User = get_user_model()


class VendorTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create(
            email="admin@vendor.test", username="adminvendor",
            is_staff=True, is_superuser=True, role='admin'
        )
        self.admin.set_password("Admin@123")
        self.admin.save()

        # Approved vendor
        self.vendor_user = User.objects.create(
            email="vendor@test.com", username="vendoruser",
            role='vendor'
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            shop_name="Test Shop",
            business_type="individual",
            business_phone="9876543210",
            business_email="shop@test.com",
            status='approved',
            is_active=True
        )

        # Second vendor for isolation tests
        self.vendor_user2 = User.objects.create(
            email="vendor2@test.com", username="vendoruser2",
            role='vendor'
        )
        self.vendor_profile2 = VendorProfile.objects.create(
            user=self.vendor_user2,
            shop_name="Test Shop 2",
            business_type="individual",
            business_phone="9876543211",
            business_email="shop2@test.com",
            status='approved',
            is_active=True
        )

        # Pending vendor
        self.pending_vendor_user = User.objects.create(
            email="pending@test.com", username="pendingvendor",
            role='vendor'
        )
        self.pending_vendor_profile = VendorProfile.objects.create(
            user=self.pending_vendor_user,
            shop_name="Pending Shop",
            business_type="individual",
            business_phone="9876543212",
            business_email="pending@test.com",
            status='pending',
            is_active=False
        )

        self.customer = User.objects.create(
            email="customer@vendor.test", username="customervendor"
        )

        self.category = Category.objects.create(
            name="Vendor Category", slug="vendor-category"
        )
        self.brand = Brand.objects.create(
            name="Vendor Brand", slug="vendor-brand"
        )
        self.storage_attr = AttributeType.objects.create(
            name="VendorStorage"
        )

        # Vendor 1's product
        self.vendor_product = Product.objects.create(
            name="Vendor Product One",
            category=self.category,
            brand=self.brand,
            price=5000,
            discount_price=4500,
            stock=0,
            has_variants=True,
            is_active=True,
            vendor=self.vendor_profile
        )
        self.vendor_variant = ProductVariant.objects.create(
            product=self.vendor_product,
            stock=20,
            price=5000
        )
        VariantAttribute.objects.create(
            variant=self.vendor_variant,
            attribute_type=self.storage_attr,
            value="64GB"
        )

        # Vendor 2's product
        self.vendor2_product = Product.objects.create(
            name="Vendor 2 Product",
            category=self.category,
            brand=self.brand,
            price=3000,
            stock=30,
            has_variants=False,
            is_active=True,
            vendor=self.vendor_profile2
        )

        self.address = Address.objects.create(
            user=self.customer,
            full_name="Test Customer",
            phone_number="9876543210",
            address_line_1="123 Street",
            city="Chennai",
            state="TN",
            postal_code="600001",
            country="India",
            address_type="both",
            is_default=True
        )

    def auth_vendor(self):
        self.client.force_authenticate(user=self.vendor_user)

    def auth_vendor2(self):
        self.client.force_authenticate(user=self.vendor_user2)

    def auth_admin(self):
        self.client.force_authenticate(user=self.admin)

    def auth_customer(self):
        self.client.force_authenticate(user=self.customer)


# ─────────────────────────────────────────────────────────────
# Vendor Registration Tests
# ─────────────────────────────────────────────────────────────

@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
)
class VendorRegistrationTests(VendorTestBase):

    def test_vendor_registration_creates_profile(self):
        OTP.objects.create(contact="newvendor@test.com", otp="123456")
        res = self.client.post('/api/vendors/register/', {
            "email": "newvendor@test.com",
            "otp": "123456",
            "shop_name": "New Test Shop",
            "business_type": "individual",
            "business_phone": "9876540000",
            "business_email": "newshop@test.com",
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            VendorProfile.objects.filter(shop_name="New Test Shop").exists()
        )

    def test_vendor_registration_status_pending(self):
        OTP.objects.create(contact="newvendor2@test.com", otp="123456")
        res = self.client.post('/api/vendors/register/', {
            "email": "newvendor2@test.com",
            "otp": "123456",
            "shop_name": "Another New Shop",
            "business_type": "individual",
            "business_phone": "9876540001",
            "business_email": "another@test.com",
        }, format='json')
        self.assertEqual(res.data['vendor_profile']['status'], 'pending')
        self.assertFalse(res.data['vendor_profile']['is_active'])

    def test_vendor_registration_role_in_response(self):
        OTP.objects.create(contact="newvendor3@test.com", otp="123456")
        res = self.client.post('/api/vendors/register/', {
            "email": "newvendor3@test.com",
            "otp": "123456",
            "shop_name": "Third New Shop",
            "business_type": "individual",
            "business_phone": "9876540002",
            "business_email": "third@test.com",
        }, format='json')
        self.assertEqual(res.data['role'], 'vendor')

    def test_duplicate_shop_name_fails(self):
        OTP.objects.create(contact="dupvendor@test.com", otp="123456")
        res = self.client.post('/api/vendors/register/', {
            "email": "dupvendor@test.com",
            "otp": "123456",
            "shop_name": "Test Shop",   # already exists
            "business_type": "individual",
            "business_phone": "9876540003",
            "business_email": "dup@test.com",
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_otp_fails(self):
        OTP.objects.create(contact="wrongotp@test.com", otp="123456")
        res = self.client.post('/api/vendors/register/', {
            "email": "wrongotp@test.com",
            "otp": "000000",
            "shop_name": "Wrong OTP Shop",
            "business_type": "individual",
            "business_phone": "9876540004",
            "business_email": "wrongotp@test.com",
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_email_cannot_register_as_vendor(self):
        OTP.objects.create(
            contact=self.customer.email, otp="123456"
        )
        res = self.client.post('/api/vendors/register/', {
            "email": self.customer.email,
            "otp": "123456",
            "shop_name": "Customer Trying Vendor",
            "business_type": "individual",
            "business_phone": "9876540005",
            "business_email": "customer@test.com",
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
# Vendor Profile Tests
# ─────────────────────────────────────────────────────────────

class VendorProfileTests(VendorTestBase):

    def test_vendor_can_view_own_profile(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/profile/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['shop_name'], 'Test Shop')

    def test_customer_cannot_view_vendor_profile(self):
        self.auth_customer()
        res = self.client.get('/api/vendors/profile/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_vendor_cannot_access_vendor_apis(self):
        self.client.force_authenticate(user=self.pending_vendor_user)
        res = self.client.get('/api/vendors/products/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_can_update_profile(self):
        self.auth_vendor()
        res = self.client.patch('/api/vendors/profile/', {
            "shop_description": "Updated description for testing"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.vendor_profile.refresh_from_db()
        self.assertEqual(
            self.vendor_profile.shop_description,
            "Updated description for testing"
        )


# ─────────────────────────────────────────────────────────────
# Vendor Product Tests
# ─────────────────────────────────────────────────────────────

class VendorProductTests(VendorTestBase):

    def test_vendor_sees_only_own_products(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/products/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [p['name'] for p in res.data['results']]
        self.assertIn('Vendor Product One', names)
        self.assertNotIn('Vendor 2 Product', names)

    def test_vendor2_sees_only_own_products(self):
        self.auth_vendor2()
        res = self.client.get('/api/vendors/products/')
        names = [p['name'] for p in res.data['results']]
        self.assertIn('Vendor 2 Product', names)
        self.assertNotIn('Vendor Product One', names)

    def test_vendor_create_product(self):
        self.auth_vendor()
        res = self.client.post('/api/vendors/products/', {
            "name": "New Vendor Product",
            "category": self.category.id,
            "brand": self.brand.id,
            "price": "3999.00",
            "stock": 0,
            "has_variants": False,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        product = Product.objects.get(name="New Vendor Product")
        self.assertEqual(product.vendor, self.vendor_profile)

    def test_vendor_product_starts_inactive(self):
        self.auth_vendor()
        res = self.client.post('/api/vendors/products/', {
            "name": "Inactive Start Product",
            "category": self.category.id,
            "brand": self.brand.id,
            "price": "1999.00",
            "stock": 10,
            "has_variants": False,
        }, format='json')
        self.assertFalse(res.data['is_active'])

    def test_vendor_cannot_access_other_vendors_product(self):
        self.auth_vendor()
        res = self.client.get(
            f'/api/vendors/products/{self.vendor2_product.slug}/'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_vendor_cannot_edit_other_vendors_product(self):
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/products/{self.vendor2_product.slug}/',
            {"price": "100.00"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_vendor_soft_delete_own_product(self):
        self.auth_vendor()
        res = self.client.delete(
            f'/api/vendors/products/{self.vendor_product.slug}/'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.vendor_product.refresh_from_db()
        self.assertFalse(self.vendor_product.is_active)

    def test_vendor_add_variant(self):
        self.auth_vendor()
        res = self.client.post(
            f'/api/vendors/products/{self.vendor_product.slug}/variants/',
            {
                "stock": 15,
                "price": "5000.00",
                "attributes": [
                    {"attribute_type_id": self.storage_attr.id, "value": "128GB"}
                ]
            },
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_vendor_cannot_add_variant_to_others_product(self):
        self.auth_vendor()
        res = self.client.post(
            f'/api/vendors/products/{self.vendor2_product.slug}/variants/',
            {"stock": 10, "price": "3000.00"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────
# Vendor Inventory Tests
# ─────────────────────────────────────────────────────────────

class VendorInventoryTests(VendorTestBase):

    def test_vendor_views_inventory(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/inventory/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('summary', res.data)
        self.assertIn('products', res.data)

    def test_inventory_summary_has_correct_fields(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/inventory/')
        summary = res.data['summary']
        self.assertIn('total_products', summary)
        self.assertIn('in_stock', summary)
        self.assertIn('low_stock', summary)
        self.assertIn('out_of_stock', summary)
        self.assertIn('total_stock_value', summary)

    def test_update_variant_stock(self):
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/inventory/{self.vendor_product.slug}/variants/{self.vendor_variant.sku}/stock/',
            {"stock": 5},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['stock_status'], 'low_stock')
        self.vendor_variant.refresh_from_db()
        self.assertEqual(self.vendor_variant.stock, 5)

    def test_update_stock_to_zero_gives_out_of_stock(self):
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/inventory/{self.vendor_product.slug}/variants/{self.vendor_variant.sku}/stock/',
            {"stock": 0},
            format='json'
        )
        self.assertEqual(res.data['stock_status'], 'out_of_stock')

    def test_update_stock_above_10_gives_in_stock(self):
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/inventory/{self.vendor_product.slug}/variants/{self.vendor_variant.sku}/stock/',
            {"stock": 50},
            format='json'
        )
        self.assertEqual(res.data['stock_status'], 'in_stock')

    def test_negative_stock_fails(self):
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/inventory/{self.vendor_product.slug}/variants/{self.vendor_variant.sku}/stock/',
            {"stock": -5},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_stock_update(self):
        self.auth_vendor()
        res = self.client.post('/api/vendors/inventory/bulk-update/', {
            "updates": [
                {"sku": self.vendor_variant.sku, "stock": 100},
                {"sku": "FAKE_SKU_NOT_EXISTS", "stock": 50},
            ]
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['updated_count'], 1)
        self.assertEqual(res.data['skipped_count'], 1)
        self.assertIn("FAKE_SKU_NOT_EXISTS", res.data['skipped_skus'])

    def test_low_stock_alert(self):
        self.vendor_variant.stock = 3
        self.vendor_variant.save()
        self.auth_vendor()
        res = self.client.get('/api/vendors/inventory/low-stock/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(res.data['total_alerts'], 0)

    def test_vendor_cannot_update_others_inventory(self):
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/inventory/{self.vendor2_product.slug}/stock/',
            {"stock": 999},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────
# Vendor Order Tests
# ─────────────────────────────────────────────────────────────

class VendorOrderTests(VendorTestBase):

    def setUp(self):
        super().setUp()
        # Create an order containing vendor's product
        self.order = Order.objects.create(
            user=self.customer,
            shipping_address=self.address,
            billing_address=self.address,
            payment_method='cod',
            payment_status='pending',
            subtotal=5000,
            shipping_fee=0,
            total=5000,
            status='confirmed'
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.vendor_product,
            variant=self.vendor_variant,
            vendor=self.vendor_profile,
            product_name=self.vendor_product.name,
            unit_price=5000,
            quantity=1,
            commission_rate=10,
            commission_amount=500,
            vendor_payout=4500
        )

    def test_vendor_sees_orders_with_their_items(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/orders/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)

    def test_vendor2_cannot_see_vendor1_orders(self):
        self.auth_vendor2()
        res = self.client.get('/api/vendors/orders/')
        self.assertEqual(res.data['count'], 0)

    def test_vendor_order_shows_only_own_items(self):
        # Add vendor2 item to same order
        OrderItem.objects.create(
            order=self.order,
            product=self.vendor2_product,
            vendor=self.vendor_profile2,
            product_name=self.vendor2_product.name,
            unit_price=3000,
            quantity=1,
            commission_rate=10,
            commission_amount=300,
            vendor_payout=2700
        )
        self.auth_vendor()
        res = self.client.get(f'/api/vendors/orders/{self.order.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        vendor_items = res.data['vendor_items']
        self.assertEqual(len(vendor_items), 1)
        self.assertEqual(
            vendor_items[0]['product_name'], self.vendor_product.name
        )

    def test_vendor_order_has_payout_info(self):
        self.auth_vendor()
        res = self.client.get(f'/api/vendors/orders/{self.order.id}/')
        self.assertIn('vendor_total_payout', res.data)
        self.assertEqual(float(res.data['vendor_total_payout']), 4500.0)

    def test_vendor_filter_orders_by_status(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/orders/?status=confirmed')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)

        res = self.client.get('/api/vendors/orders/?status=shipped')
        self.assertEqual(res.data['count'], 0)

    def test_vendor_update_item_status(self):
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/orders/{self.order.id}/items/{self.order_item.id}/status/',
            {"status": "shipped", "note": "Dispatched via BlueDart"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_vendor_cannot_update_other_vendors_item(self):
        other_item = OrderItem.objects.create(
            order=self.order,
            product=self.vendor2_product,
            vendor=self.vendor_profile2,
            product_name=self.vendor2_product.name,
            unit_price=3000,
            quantity=1,
            commission_rate=10,
            commission_amount=300,
            vendor_payout=2700
        )
        self.auth_vendor()
        res = self.client.patch(
            f'/api/vendors/orders/{self.order.id}/items/{other_item.id}/status/',
            {"status": "shipped"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────
# Vendor Dashboard Tests
# ─────────────────────────────────────────────────────────────

class VendorDashboardTests(VendorTestBase):

    def setUp(self):
        super().setUp()
        self.order = Order.objects.create(
            user=self.customer,
            shipping_address=self.address,
            billing_address=self.address,
            payment_method='cod',
            payment_status='pending',
            subtotal=5000,
            shipping_fee=0,
            total=5000,
            status='confirmed'
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.vendor_product,
            vendor=self.vendor_profile,
            product_name=self.vendor_product.name,
            unit_price=5000,
            quantity=2,
            commission_rate=10,
            commission_amount=1000,
            vendor_payout=9000
        )

    def test_dashboard_returns_200(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_dashboard_has_all_required_fields(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/dashboard/')
        required = [
            'shop_name', 'total_revenue', 'total_payout',
            'total_commission_paid', 'total_orders', 'total_products',
            'this_month_revenue', 'low_stock_count', 'out_of_stock_count',
            'orders_by_status', 'revenue_last_7_days',
            'revenue_last_30_days', 'best_selling_products', 'recent_orders'
        ]
        for field in required:
            self.assertIn(field, res.data, f"Missing field: {field}")

    def test_dashboard_total_orders_correct(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(res.data['total_orders'], 1)

    def test_dashboard_revenue_correct(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(float(res.data['total_revenue']), 10000.0)

    def test_dashboard_payout_correct(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(float(res.data['total_payout']), 9000.0)

    def test_dashboard_has_7_day_chart_data(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(len(res.data['revenue_last_7_days']), 7)

    def test_dashboard_has_30_day_chart_data(self):
        self.auth_vendor()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(len(res.data['revenue_last_30_days']), 30)

    def test_dashboard_vendor2_sees_own_data(self):
        self.auth_vendor2()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(res.data['total_orders'], 0)
        self.assertEqual(float(res.data['total_revenue']), 0.0)

    def test_customer_cannot_access_dashboard(self):
        self.auth_customer()
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_vendor_cannot_access_dashboard(self):
        self.client.force_authenticate(user=self.pending_vendor_user)
        res = self.client.get('/api/vendors/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)