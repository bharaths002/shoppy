from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from products.models import (
    Product, Category, Brand,
    ProductVariant, VariantAttribute, AttributeType
)

User = get_user_model()


class CartTestBase(TestCase):
    """Shared setup for all cart tests"""

    def setUp(self):
        self.client = APIClient()

        # Users
        self.user_a = User.objects.create(email="usera@test.com", username="usera")
        self.user_b = User.objects.create(email="userb@test.com", username="userb")

        # Category and Brand
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.brand = Brand.objects.create(name="Samsung", slug="samsung")

        # Attribute types
        self.storage_attr = AttributeType.objects.create(name="Storage")
        self.color_attr = AttributeType.objects.create(name="Color")

        # Simple product — no variants
        self.simple_product = Product.objects.create(
            name="Simple Earphones",
            category=self.category,
            brand=self.brand,
            price=999,
            stock=50,
            has_variants=False,
            is_active=True,
        )

        # Variant product
        self.variant_product = Product.objects.create(
            name="Samsung Galaxy S25",
            category=self.category,
            brand=self.brand,
            price=79999,
            discount_price=74999,
            stock=0,
            has_variants=True,
            is_active=True,
        )

        # Variants
        self.variant_1 = ProductVariant.objects.create(
            product=self.variant_product,
            stock=25,
            price=79999,
        )
        VariantAttribute.objects.create(
            variant=self.variant_1,
            attribute_type=self.storage_attr,
            value="128GB"
        )

        self.variant_2 = ProductVariant.objects.create(
            product=self.variant_product,
            stock=10,
            price=89999,
        )
        VariantAttribute.objects.create(
            variant=self.variant_2,
            attribute_type=self.storage_attr,
            value="256GB"
        )

        # Out of stock variant
        self.out_of_stock_variant = ProductVariant.objects.create(
            product=self.variant_product,
            stock=0,
            price=99999,
        )
        VariantAttribute.objects.create(
            variant=self.out_of_stock_variant,
            attribute_type=self.storage_attr,
            value="512GB"
        )

        # Inactive product
        self.inactive_product = Product.objects.create(
            name="Inactive Phone",
            category=self.category,
            brand=self.brand,
            price=50000,
            stock=10,
            has_variants=False,
            is_active=False,
        )

        self.cart_url = '/api/cart/'
        self.items_url = '/api/cart/items/'

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def unauthenticate(self):
        self.client.force_authenticate(user=None)

    def add_simple_item(self, quantity=1):
        return self.client.post(self.items_url, {
            "product_id": str(self.simple_product.id),
            "quantity": quantity
        }, format='json')

    def add_variant_item(self, variant_id=None, quantity=1):
        return self.client.post(self.items_url, {
            "product_id": str(self.variant_product.id),
            "variant_id": variant_id or self.variant_1.id,
            "quantity": quantity
        }, format='json')


# ─────────────────────────────────────────────────────────────
# View Cart Tests
# ─────────────────────────────────────────────────────────────

class ViewCartTests(CartTestBase):

    def test_logged_in_user_can_view_empty_cart(self):
        """Authenticated user sees empty cart"""
        self.authenticate(self.user_a)
        res = self.client.get(self.cart_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['total_items'], 0)
        self.assertEqual(len(res.data['items']), 0)

    def test_guest_can_view_cart(self):
        """Guest user can view cart without token"""
        self.unauthenticate()
        res = self.client.get(self.cart_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('items', res.data)

    def test_cart_response_has_required_fields(self):
        """Cart response contains all expected fields"""
        self.authenticate(self.user_a)
        res = self.client.get(self.cart_url)
        self.assertIn('id', res.data)
        self.assertIn('total_items', res.data)
        self.assertIn('subtotal', res.data)
        self.assertIn('items', res.data)
        self.assertIn('updated_at', res.data)

    def test_user_a_cannot_see_user_b_cart(self):
        """Each user sees only their own cart"""
        self.authenticate(self.user_a)
        self.add_simple_item()

        self.authenticate(self.user_b)
        res = self.client.get(self.cart_url)
        self.assertEqual(res.data['total_items'], 0)


# ─────────────────────────────────────────────────────────────
# Add to Cart Tests
# ─────────────────────────────────────────────────────────────

class AddToCartTests(CartTestBase):

    # ── Happy Path ────────────────────────────────────────

    def test_add_simple_product_to_cart(self):
        """Add a product with no variants to cart"""
        self.authenticate(self.user_a)
        res = self.add_simple_item(quantity=2)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Item added to cart.')
        self.assertEqual(res.data['cart']['total_items'], 2)

    def test_add_variant_product_to_cart(self):
        """Add a product with a variant to cart"""
        self.authenticate(self.user_a)
        res = self.add_variant_item(variant_id=self.variant_1.id, quantity=1)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Item added to cart.')

    def test_add_same_item_increments_quantity(self):
        """Adding same item again increments quantity"""
        self.authenticate(self.user_a)
        self.add_simple_item(quantity=1)
        res = self.add_simple_item(quantity=2)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Cart updated.')
        self.assertEqual(res.data['cart']['total_items'], 3)

    def test_add_different_variants_as_separate_items(self):
        """Different variants of same product are separate cart items"""
        self.authenticate(self.user_a)
        self.add_variant_item(variant_id=self.variant_1.id, quantity=1)
        self.add_variant_item(variant_id=self.variant_2.id, quantity=1)
        res = self.client.get(self.cart_url)
        self.assertEqual(len(res.data['items']), 2)

    def test_guest_can_add_to_cart(self):
        """Guest user can add items without token"""
        self.unauthenticate()
        res = self.add_simple_item(quantity=1)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['cart']['total_items'], 1)

    def test_cart_subtotal_calculated_correctly(self):
        """Subtotal equals unit price × quantity"""
        self.authenticate(self.user_a)
        self.add_simple_item(quantity=3)
        res = self.client.get(self.cart_url)
        expected_subtotal = float(self.simple_product.effective_price) * 3
        self.assertEqual(float(res.data['subtotal']), expected_subtotal)

    def test_cart_item_has_product_info(self):
        """Cart item contains product name and slug"""
        self.authenticate(self.user_a)
        self.add_simple_item()
        res = self.client.get(self.cart_url)
        item = res.data['items'][0]
        self.assertIn('product', item)
        self.assertEqual(item['product']['name'], 'Simple Earphones')

    def test_cart_item_has_variant_attributes(self):
        """Cart item shows variant attributes"""
        self.authenticate(self.user_a)
        self.add_variant_item(variant_id=self.variant_1.id)
        res = self.client.get(self.cart_url)
        item = res.data['items'][0]
        self.assertIsNotNone(item['variant'])
        self.assertEqual(len(item['variant']['attributes']), 1)
        self.assertEqual(item['variant']['attributes'][0]['value'], '128GB')

    # ── Edge Cases ────────────────────────────────────────

    def test_add_inactive_product_fails(self):
        """Cannot add inactive product to cart"""
        self.authenticate(self.user_a)
        res = self.client.post(self.items_url, {
            "product_id": str(self.inactive_product.id),
            "quantity": 1
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", res.data)

    def test_add_invalid_product_id_fails(self):
        """Invalid UUID returns 400"""
        self.authenticate(self.user_a)
        res = self.client.post(self.items_url, {
            "product_id": "00000000-0000-0000-0000-000000000000",
            "quantity": 1
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_variant_product_without_variant_id_fails(self):
        """Variant product requires variant_id"""
        self.authenticate(self.user_a)
        res = self.client.post(self.items_url, {
            "product_id": str(self.variant_product.id),
            "quantity": 1
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("variant_id", res.data)

    def test_add_invalid_variant_id_fails(self):
        """Variant not belonging to product returns 400"""
        self.authenticate(self.user_a)
        res = self.client.post(self.items_url, {
            "product_id": str(self.variant_product.id),
            "variant_id": 99999,
            "quantity": 1
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_zero_quantity_fails(self):
        """Quantity must be at least 1"""
        self.authenticate(self.user_a)
        res = self.client.post(self.items_url, {
            "product_id": str(self.simple_product.id),
            "quantity": 0
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_missing_product_id_fails(self):
        """Missing product_id returns 400"""
        self.authenticate(self.user_a)
        res = self.client.post(self.items_url, {
            "quantity": 1
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Stock Validation ──────────────────────────────────

    def test_add_more_than_stock_fails(self):
        """Cannot add quantity greater than available stock"""
        self.authenticate(self.user_a)
        res = self.add_simple_item(quantity=100)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", res.data)

    def test_add_out_of_stock_variant_fails(self):
        """Cannot add out of stock variant"""
        self.authenticate(self.user_a)
        res = self.add_variant_item(
            variant_id=self.out_of_stock_variant.id,
            quantity=1
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_incrementing_beyond_stock_fails(self):
        """Adding more of same item beyond stock fails"""
        self.authenticate(self.user_a)
        self.add_simple_item(quantity=45)
        res = self.add_simple_item(quantity=10)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", res.data)


# ─────────────────────────────────────────────────────────────
# Update Cart Item Tests
# ─────────────────────────────────────────────────────────────

class UpdateCartItemTests(CartTestBase):

    def setUp(self):
        super().setUp()
        self.authenticate(self.user_a)
        res = self.add_simple_item(quantity=2)
        self.item_id = res.data['cart']['items'][0]['id']

    def test_update_quantity_success(self):
        """Update cart item quantity successfully"""
        res = self.client.patch(
            f'/api/cart/items/{self.item_id}/',
            {"quantity": 5},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Quantity updated.')
        self.assertEqual(res.data['cart']['total_items'], 5)

    def test_update_quantity_above_stock_fails(self):
        """Cannot update quantity above available stock"""
        res = self.client.patch(
            f'/api/cart/items/{self.item_id}/',
            {"quantity": 200},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stock", res.data['error'])

    def test_update_quantity_zero_fails(self):
        """Quantity cannot be set to zero"""
        res = self.client.patch(
            f'/api/cart/items/{self.item_id}/',
            {"quantity": 0},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_nonexistent_item_fails(self):
        """Updating non-existent cart item returns 404"""
        res = self.client.patch(
            '/api/cart/items/99999/',
            {"quantity": 1},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_update_other_users_cart_item(self):
        """User B cannot update User A's cart item"""
        self.authenticate(self.user_b)
        res = self.client.patch(
            f'/api/cart/items/{self.item_id}/',
            {"quantity": 1},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────
# Remove Cart Item Tests
# ─────────────────────────────────────────────────────────────

class RemoveCartItemTests(CartTestBase):

    def setUp(self):
        super().setUp()
        self.authenticate(self.user_a)
        res = self.add_simple_item(quantity=2)
        self.item_id = res.data['cart']['items'][0]['id']

    def test_remove_item_success(self):
        """Remove item from cart successfully"""
        res = self.client.delete(f'/api/cart/items/{self.item_id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Item removed.')
        self.assertEqual(res.data['cart']['total_items'], 0)

    def test_remove_nonexistent_item_fails(self):
        """Removing non-existent item returns 404"""
        res = self.client.delete('/api/cart/items/99999/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_remove_other_users_item(self):
        """User B cannot remove User A's cart item"""
        self.authenticate(self.user_b)
        res = self.client.delete(f'/api/cart/items/{self.item_id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

def test_remove_one_item_keeps_others(self):
    """Removing one item doesn't affect other items"""
    self.authenticate(self.user_a)

    # Add variant item and capture its ID directly
    res2 = self.add_variant_item(variant_id=self.variant_1.id, quantity=1)

    # ✅ Find the variant item by looking for the one that's NOT self.item_id
    all_items = res2.data['cart']['items']
    item_2_id = next(
        item['id'] for item in all_items
        if item['id'] != self.item_id
    )

    # Remove the simple item
    self.client.delete(f'/api/cart/items/{self.item_id}/')

    # Check only variant item remains
    res = self.client.get(self.cart_url)
    self.assertEqual(len(res.data['items']), 1)
    self.assertEqual(res.data['items'][0]['id'], item_2_id)  # ✅ correct item remains


# ─────────────────────────────────────────────────────────────
# Clear Cart Tests
# ─────────────────────────────────────────────────────────────

class ClearCartTests(CartTestBase):

    def test_clear_cart_success(self):
        """Clear entire cart successfully"""
        self.authenticate(self.user_a)
        self.add_simple_item(quantity=2)
        self.add_variant_item(variant_id=self.variant_1.id, quantity=1)

        res = self.client.delete(self.cart_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Cart cleared successfully.')

        cart_res = self.client.get(self.cart_url)
        self.assertEqual(cart_res.data['total_items'], 0)

    def test_clear_empty_cart(self):
        """Clearing already empty cart works fine"""
        self.authenticate(self.user_a)
        res = self.client.delete(self.cart_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_clear_cart_only_affects_own_cart(self):
        """Clearing User A cart does not affect User B cart"""
        self.authenticate(self.user_b)
        self.add_simple_item(quantity=3)

        self.authenticate(self.user_a)
        self.client.delete(self.cart_url)

        self.authenticate(self.user_b)
        res = self.client.get(self.cart_url)
        self.assertEqual(res.data['total_items'], 3)


# ─────────────────────────────────────────────────────────────
# Guest Cart & Merge Tests
# ─────────────────────────────────────────────────────────────

class GuestCartTests(CartTestBase):

    def test_guest_cart_created_on_first_request(self):
        """Guest cart is created on first interaction"""
        self.unauthenticate()
        res = self.client.get(self.cart_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('items', res.data)

    def test_guest_can_add_and_view_items(self):
        """Guest can add items and view them"""
        self.unauthenticate()
        self.add_simple_item(quantity=2)
        res = self.client.get(self.cart_url)
        self.assertEqual(res.data['total_items'], 2)

    def test_guest_cart_merges_on_login(self):
        """Guest cart items merge into user cart on OTP login"""
        from cart.utils import merge_guest_cart_to_user
        from cart.models import Cart

        # Guest adds items
        self.unauthenticate()
        self.add_simple_item(quantity=2)

        # Simulate session
        session = self.client.session
        session.save()
        session_key = session.session_key

        # Create a mock request with session
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.session = session

        # Merge guest cart into user
        merge_guest_cart_to_user(request, self.user_a)

        # User cart should now have the items
        user_cart = Cart.objects.filter(user=self.user_a).first()
        self.assertIsNotNone(user_cart)
        self.assertEqual(user_cart.items.count(), 1)
        self.assertEqual(user_cart.items.first().quantity, 2)

    def test_guest_cart_deleted_after_merge(self):
        """Guest cart is deleted after merging into user cart"""
        from cart.utils import merge_guest_cart_to_user
        from cart.models import Cart

        self.unauthenticate()
        self.add_simple_item(quantity=1)

        session = self.client.session
        session.save()
        session_key = session.session_key

        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.session = session

        merge_guest_cart_to_user(request, self.user_a)

        guest_cart_exists = Cart.objects.filter(
            session_key=session_key
        ).exists()
        self.assertFalse(guest_cart_exists)