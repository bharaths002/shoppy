from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from unittest.mock import patch
from products.models import (
    Product, Category, Brand, ProductVariant,
    VariantAttribute, AttributeType
)
from accounts.models import Address
from cart.models import Cart, CartItem
from orders.models import Order, OrderItem, OrderStatusHistory

User = get_user_model()


class OrderTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create(
            email="admin@test.com", username="adminorder",
            is_staff=True, is_superuser=True
        )
        self.admin.set_password("Admin@123")
        self.admin.save()

        self.customer = User.objects.create(
            email="customer@test.com", username="customerorder"
        )
        self.customer2 = User.objects.create(
            email="customer2@test.com", username="customerorder2"
        )

        self.category = Category.objects.create(
            name="Electronics", slug="electronics-order"
        )
        self.brand = Brand.objects.create(
            name="Samsung", slug="samsung-order"
        )

        self.simple_product = Product.objects.create(
            name="Samsung Buds",
            category=self.category,
            brand=self.brand,
            price=2999,
            stock=50,
            has_variants=False,
            is_active=True,
        )

        self.variant_product = Product.objects.create(
            name="Samsung Galaxy",
            category=self.category,
            brand=self.brand,
            price=79999,
            discount_price=74999,
            stock=0,
            has_variants=True,
            is_active=True,
        )
        self.storage_attr = AttributeType.objects.create(
            name="StorageOrder"
        )
        self.variant = ProductVariant.objects.create(
            product=self.variant_product, stock=25, price=79999
        )
        VariantAttribute.objects.create(
            variant=self.variant,
            attribute_type=self.storage_attr,
            value="128GB"
        )

        self.address = Address.objects.create(
            user=self.customer,
            full_name="Test Customer",
            phone_number="9876543210",
            address_line_1="123 Test Street",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600001",
            country="India",
            address_type="both",
            is_default=True
        )

        self.billing_address = Address.objects.create(
            user=self.customer,
            full_name="Test Customer Billing",
            phone_number="9876543210",
            address_line_1="456 Billing Street",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600002",
            country="India",
            address_type="billing",
            is_default=False
        )

    def auth_customer(self):
        self.client.force_authenticate(user=self.customer)

    def auth_admin(self):
        self.client.force_authenticate(user=self.admin)

    def add_item_to_cart(self, product_id=None, variant_id=None, quantity=1):
        cart, _ = Cart.objects.get_or_create(user=self.customer)
        product = Product.objects.get(id=product_id) if product_id else self.simple_product
        variant = ProductVariant.objects.get(id=variant_id) if variant_id else None
        CartItem.objects.get_or_create(
            cart=cart, product=product, variant=variant,
            defaults={'quantity': quantity}
        )
        return cart

    def place_cod_order(self):
        self.add_item_to_cart(quantity=1)
        self.auth_customer()
        return self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": True,
            "payment_method": "cod"
        }, format='json')


# ─────────────────────────────────────────────────────────────
# Create Order Tests
# ─────────────────────────────────────────────────────────────

class CreateOrderTests(OrderTestBase):

    def test_cod_order_confirmed_immediately(self):
        res = self.place_cod_order()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['order']['status'], 'confirmed')
        self.assertEqual(res.data['message'], 'Order placed successfully.')

    def test_cod_order_clears_cart(self):
        self.place_cod_order()
        cart = Cart.objects.get(user=self.customer)
        self.assertEqual(cart.items.count(), 0)

    def test_cod_order_deducts_stock(self):
        old_stock = self.simple_product.stock
        self.place_cod_order()
        self.simple_product.refresh_from_db()
        self.assertEqual(self.simple_product.stock, old_stock - 1)

    def test_cod_order_creates_status_history(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        history = OrderStatusHistory.objects.filter(order__id=order_id)
        statuses = [h.status for h in history]
        self.assertIn('pending', statuses)
        self.assertIn('confirmed', statuses)

    def test_order_with_same_billing_as_shipping(self):
        self.add_item_to_cart()
        self.auth_customer()
        res = self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": True,
            "payment_method": "cod"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_order_with_different_billing_address(self):
        self.add_item_to_cart()
        self.auth_customer()
        res = self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": False,
            "billing_address_id": self.billing_address.id,
            "payment_method": "cod"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_empty_cart_order_fails(self):
        self.auth_customer()
        res = self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": True,
            "payment_method": "cod"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cart', res.data)

    def test_invalid_address_fails(self):
        self.add_item_to_cart()
        self.auth_customer()
        res = self.client.post('/api/orders/create/', {
            "shipping_address_id": 99999,
            "same_as_shipping": True,
            "payment_method": "cod"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_billing_address_when_not_same(self):
        self.add_item_to_cart()
        self.auth_customer()
        res = self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": False,
            "payment_method": "cod"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_order(self):
        self.client.force_authenticate(user=None)
        res = self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": True,
            "payment_method": "cod"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('orders.razorpay_utils.get_razorpay_client')
    def test_upi_order_creates_razorpay_order(self, mock_razorpay):
        mock_razorpay.return_value.order.create.return_value = {
            'id': 'order_test_123',
            'amount': 299900,
            'currency': 'INR'
        }
        self.add_item_to_cart()
        self.auth_customer()
        res = self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": True,
            "payment_method": "upi"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('razorpay_order_id', res.data)
        self.assertEqual(res.data['razorpay_order_id'], 'order_test_123')

    @patch('orders.razorpay_utils.get_razorpay_client')
    def test_upi_order_does_not_clear_cart(self, mock_razorpay):
        mock_razorpay.return_value.order.create.return_value = {
            'id': 'order_test_123',
            'amount': 299900,
            'currency': 'INR'
        }
        self.add_item_to_cart()
        self.auth_customer()
        self.client.post('/api/orders/create/', {
            "shipping_address_id": self.address.id,
            "same_as_shipping": True,
            "payment_method": "upi"
        }, format='json')
        cart = Cart.objects.get(user=self.customer)
        self.assertGreater(cart.items.count(), 0)


# ─────────────────────────────────────────────────────────────
# Payment Verification Tests
# ─────────────────────────────────────────────────────────────

class PaymentVerificationTests(OrderTestBase):

    def create_pending_order(self):
        self.add_item_to_cart()
        order = Order.objects.create(
            user=self.customer,
            shipping_address=self.address,
            billing_address=self.address,
            payment_method='upi',
            subtotal=2999,
            shipping_fee=0,
            total=2999,
            status='pending',
            payment_status='pending',
            razorpay_order_id='order_test_fake123'
        )
        return order

    @patch('orders.razorpay_utils.get_razorpay_client')
    def test_valid_payment_confirms_order(self, mock_razorpay):
        mock_razorpay.return_value.utility.verify_payment_signature.return_value = True
        order = self.create_pending_order()
        self.auth_customer()
        res = self.client.post('/api/orders/verify-payment/', {
            "order_id": str(order.id),
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "valid_signature"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, 'confirmed')
        self.assertEqual(order.payment_status, 'paid')

    @patch('orders.razorpay_utils.get_razorpay_client')
    def test_invalid_signature_fails(self, mock_razorpay):
        from razorpay.errors import SignatureVerificationError
        mock_razorpay.return_value.utility.verify_payment_signature.side_effect = \
            SignatureVerificationError('Invalid', {})
        order = self.create_pending_order()
        self.auth_customer()
        res = self.client.post('/api/orders/verify-payment/', {
            "order_id": str(order.id),
            "razorpay_payment_id": "pay_fake",
            "razorpay_signature": "bad_signature"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'failed')

    def test_missing_verification_fields(self):
        self.auth_customer()
        res = self.client.post('/api/orders/verify-payment/', {
            "order_id": "some-id"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_nonexistent_order(self):
        self.auth_customer()
        res = self.client.post('/api/orders/verify-payment/', {
            "order_id": "00000000-0000-0000-0000-000000000000",
            "razorpay_payment_id": "pay_123",
            "razorpay_signature": "sig_123"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────
# Order List and Detail Tests
# ─────────────────────────────────────────────────────────────

class OrderListDetailTests(OrderTestBase):

    def test_customer_sees_own_orders(self):
        self.place_cod_order()
        self.auth_customer()
        res = self.client.get('/api/orders/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

    def test_customer_cannot_see_other_orders(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.client.force_authenticate(user=self.customer2)
        res = self.client.get(f'/api/orders/{order_id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_detail_has_items(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.auth_customer()
        res = self.client.get(f'/api/orders/{order_id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(len(res.data['items']), 0)

    def test_order_detail_has_status_history(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.auth_customer()
        res = self.client.get(f'/api/orders/{order_id}/')
        self.assertIn('status_history', res.data)
        self.assertGreater(len(res.data['status_history']), 0)

    def test_unauthenticated_cannot_view_orders(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/orders/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


# ─────────────────────────────────────────────────────────────
# Cancel Order Tests
# ─────────────────────────────────────────────────────────────

class CancelOrderTests(OrderTestBase):

    def test_cancel_confirmed_order(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.auth_customer()
        res = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['order']['status'], 'cancelled')

    def test_cancel_restores_stock(self):
        old_stock = self.simple_product.stock
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.simple_product.refresh_from_db()
        self.assertEqual(self.simple_product.stock, old_stock - 1)
        self.auth_customer()
        self.client.post(f'/api/orders/{order_id}/cancel/')
        self.simple_product.refresh_from_db()
        self.assertEqual(self.simple_product.stock, old_stock)

    def test_cancel_already_cancelled_fails(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.auth_customer()
        self.client.post(f'/api/orders/{order_id}/cancel/')
        res = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_delivered_order_fails(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        order = Order.objects.get(id=order_id)
        order.status = 'delivered'
        order.save()
        self.auth_customer()
        res = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_shipped_order_fails(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        order = Order.objects.get(id=order_id)
        order.status = 'shipped'
        order.save()
        self.auth_customer()
        res = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
# Admin Order Management Tests
# ─────────────────────────────────────────────────────────────

class AdminOrderTests(OrderTestBase):

    def test_admin_sees_all_orders(self):
        self.place_cod_order()
        self.auth_admin()
        res = self.client.get('/api/orders/admin/all/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(len(res.data), 0)

    def test_admin_filter_by_status(self):
        self.place_cod_order()
        self.auth_admin()
        res = self.client.get('/api/orders/admin/all/?status=confirmed')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for order in res.data:
            self.assertEqual(order['status'], 'confirmed')

    def test_admin_update_order_status(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.auth_admin()
        res = self.client.patch(
            f'/api/orders/admin/{order_id}/status/',
            {"status": "shipped", "note": "Dispatched via BlueDart"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['order']['status'], 'shipped')

    def test_admin_invalid_status_fails(self):
        res = self.place_cod_order()
        order_id = res.data['order']['id']
        self.auth_admin()
        res = self.client.patch(
            f'/api/orders/admin/{order_id}/status/',
            {"status": "flying"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_cannot_access_admin_orders(self):
        self.auth_customer()
        res = self.client.get('/api/orders/admin/all/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
