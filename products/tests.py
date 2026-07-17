
# Create your tests here.
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import Product, Category, Brand, ProductVariant, VariantAttribute, AttributeType
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

User = get_user_model()


class ProductTestBase(TestCase):
    """Shared setup for all product tests"""

    def setUp(self):
        self.client = APIClient()

        # Admin user
        self.admin = User.objects.create(email="admin@test.com", username="admin")
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.set_password("Admin@123")
        self.admin.save()

        # Regular customer
        self.customer = User.objects.create(email="customer@test.com", username="customer123")

        # Category and Brand
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.brand = Brand.objects.create(name="Samsung", slug="samsung")

        # Attribute types
        self.storage_attr = AttributeType.objects.create(name="Storage")
        self.color_attr = AttributeType.objects.create(name="Color")

        # Sample product
        self.product = Product.objects.create(
            name="Samsung Galaxy S25",
            category=self.category,
            brand=self.brand,
            price=79999,
            discount_price=74999,
            has_variants=True,
            is_active=True,
            is_featured=True,
        )

        # Sample variant
        self.variant = ProductVariant.objects.create(
            product=self.product,
            stock=25,
            price=79999,
        )
        VariantAttribute.objects.create(
            variant=self.variant,
            attribute_type=self.storage_attr,
            value="128GB"
        )
        VariantAttribute.objects.create(
            variant=self.variant,
            attribute_type=self.color_attr,
            value="Phantom Black"
        )

    def authenticate_admin(self):
        self.client.force_authenticate(user=self.admin)

    def authenticate_customer(self):
        self.client.force_authenticate(user=self.customer)

    def unauthenticate(self):
        self.client.force_authenticate(user=None)


class ProductListTests(ProductTestBase):

    # ── Happy Path ────────────────────────────────────────

    def test_list_products_success(self):
        """Anyone can list active products"""
        res = self.client.get('/api/products/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("results", res.data)
        self.assertEqual(res.data["count"], 1)

    def test_inactive_products_not_shown(self):
        """Inactive products hidden from listing"""
        self.product.is_active = False
        self.product.save()
        res = self.client.get('/api/products/')
        self.assertEqual(res.data["count"], 0)

    def test_pagination_fields_present(self):
        """Pagination metadata returned"""
        res = self.client.get('/api/products/')
        self.assertIn("page", res.data)
        self.assertIn("total_pages", res.data)
        self.assertIn("has_next", res.data)
        self.assertIn("has_previous", res.data)

    def test_page_size_default_10(self):
        """Default page size is 10"""
        res = self.client.get('/api/products/')
        self.assertEqual(res.data["page_size"], 10)

    # ── Search ────────────────────────────────────────────

    def test_search_by_name(self):
        """Search returns matching products"""
        res = self.client.get('/api/products/?search=samsung')
        self.assertEqual(res.data["count"], 1)

    def test_search_no_match(self):
        """Search with no match returns empty"""
        res = self.client.get('/api/products/?search=nokia')
        self.assertEqual(res.data["count"], 0)

    def test_search_by_brand_name(self):
        """Search works on brand name too"""
        res = self.client.get('/api/products/?search=Samsung')
        self.assertEqual(res.data["count"], 1)

    # ── Filters ───────────────────────────────────────────

    def test_filter_by_category_slug(self):
        """Filter by category returns correct products"""
        res = self.client.get('/api/products/?category=electronics')
        self.assertEqual(res.data["count"], 1)

    def test_filter_by_invalid_category(self):
        """Invalid category slug returns 404"""
        res = self.client.get('/api/products/?category=nonexistent')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_brand_slug(self):
        """Filter by brand returns correct products"""
        res = self.client.get('/api/products/?brand=samsung')
        self.assertEqual(res.data["count"], 1)

    def test_filter_by_price_range(self):
        """Price range filter works"""
        res = self.client.get('/api/products/?min_price=50000&max_price=90000')
        self.assertEqual(res.data["count"], 1)

    def test_filter_price_range_no_match(self):
        """Price range with no match returns empty"""
        res = self.client.get('/api/products/?min_price=1000&max_price=5000')
        self.assertEqual(res.data["count"], 0)

    def test_filter_featured(self):
        """Featured filter returns only featured products"""
        res = self.client.get('/api/products/?featured=true')
        self.assertEqual(res.data["count"], 1)

    def test_ordering_price_low(self):
        """Ordering by price_low works without error"""
        res = self.client.get('/api/products/?ordering=price_low')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_ordering_price_high(self):
        """Ordering by price_high works without error"""
        res = self.client.get('/api/products/?ordering=price_high')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    # ── Edge Cases ────────────────────────────────────────

    def test_invalid_page_number_defaults_to_1(self):
        """Non-integer page param defaults gracefully"""
        res = self.client.get('/api/products/?page=abc')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["page"], 1)

    def test_page_size_capped_at_50(self):
        """Page size cannot exceed 50"""
        res = self.client.get('/api/products/?page_size=200')
        self.assertEqual(res.data["page_size"], 50)


class ProductDetailTests(ProductTestBase):

    # ── Happy Path ────────────────────────────────────────

    def test_get_product_detail_success(self):
        """Valid slug returns full product detail"""
        res = self.client.get(f'/api/products/{self.product.slug}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["name"], "Samsung Galaxy S25")
        self.assertIn("variants", res.data)
        self.assertIn("images", res.data)

    def test_product_detail_has_variants(self):
        """Variants with attributes returned in detail"""
        res = self.client.get(f'/api/products/{self.product.slug}/')
        variants = res.data["variants"]
        self.assertEqual(len(variants), 1)
        self.assertEqual(len(variants[0]["attributes"]), 2)

    def test_product_detail_discount_percent(self):
        """Discount percent calculated correctly"""
        res = self.client.get(f'/api/products/{self.product.slug}/')
        self.assertGreater(res.data["discount_percent"], 0)

    # ── Edge Cases ────────────────────────────────────────

    def test_get_nonexistent_product(self):
        """Invalid slug returns 404"""
        res = self.client.get('/api/products/nonexistent-slug/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_product_returns_404(self):
        """Inactive product not accessible"""
        self.product.is_active = False
        self.product.save()
        res = self.client.get(f'/api/products/{self.product.slug}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class ProductCRUDTests(ProductTestBase):

    # ── Create ────────────────────────────────────────────

    def test_admin_can_create_product(self):
        """Admin can create a product"""
        self.authenticate_admin()
        res = self.client.post('/api/products/', {
            "name": "iPhone 15",
            "category": self.category.id,
            "brand": self.brand.id,
            "price": "99999.00",
            "discount_price": "94999.00",
            "stock": 0,
            "has_variants": True,
            "is_active": True,
            "is_featured": False,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Product.objects.filter(name="iPhone 15").exists())

    def test_customer_cannot_create_product(self):
        """Regular customer gets 403 on create"""
        self.authenticate_customer()
        res = self.client.post('/api/products/', {
            "name": "Fake Product",
            "price": "999.00",
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_product(self):
        """Unauthenticated user gets 401 on create"""
        self.unauthenticate()
        res = self.client.post('/api/products/', {
            "name": "Fake Product",
            "price": "999.00",
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_product_discount_greater_than_price_fails(self):
        """Discount price >= original price should fail validation"""
        self.authenticate_admin()
        res = self.client.post('/api/products/', {
            "name": "Bad Product",
            "category": self.category.id,
            "price": "5000.00",
            "discount_price": "6000.00",  # greater than price
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Update ────────────────────────────────────────────

    def test_admin_can_patch_product(self):
        """Admin can partially update product"""
        self.authenticate_admin()
        res = self.client.patch(
            f'/api/products/{self.product.slug}/',
            {"discount_price": "69999.00"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(float(self.product.discount_price), 69999.00)

    def test_customer_cannot_update_product(self):
        """Customer gets 403 on update"""
        self.authenticate_customer()
        res = self.client.patch(
            f'/api/products/{self.product.slug}/',
            {"price": "100.00"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # ── Delete ────────────────────────────────────────────

    def test_admin_soft_delete(self):
        """Admin soft delete sets is_active to False"""
        self.authenticate_admin()
        res = self.client.delete(f'/api/products/{self.product.slug}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_soft_deleted_product_not_in_listing(self):
        """Soft deleted product disappears from listing"""
        self.authenticate_admin()
        self.client.delete(f'/api/products/{self.product.slug}/')
        self.unauthenticate()
        res = self.client.get('/api/products/')
        self.assertEqual(res.data["count"], 0)

    def test_customer_cannot_delete_product(self):
        """Customer gets 403 on delete"""
        self.authenticate_customer()
        res = self.client.delete(f'/api/products/{self.product.slug}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ProductImageTests(ProductTestBase):

    def test_admin_can_upload_image(self):
        """Admin can upload product images"""
        self.authenticate_admin()
        image = SimpleUploadedFile(
            "test.jpg", b"fakeimagecontent", content_type="image/jpeg"
        )
        with patch('cloudinary_storage.storage.MediaCloudinaryStorage.save',
                   return_value='products/test.jpg'), \
             patch('cloudinary_storage.storage.MediaCloudinaryStorage.url',
                   return_value='http://cloudinary.com/test.jpg'):
            res = self.client.post(
                f'/api/products/{self.product.slug}/images/',
                {"images": image, "is_primary": "true"},
                format='multipart'
            )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_no_images_returns_400(self):
        """Missing images key returns 400"""
        self.authenticate_admin()
        res = self.client.post(
            f'/api/products/{self.product.slug}/images/',
            {"is_primary": "true"},
            format='multipart'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_cannot_upload_image(self):
        """Customer cannot upload images"""
        self.authenticate_customer()
        image = SimpleUploadedFile("test.jpg", b"fakecontent", content_type="image/jpeg")
        res = self.client.post(
            f'/api/products/{self.product.slug}/images/',
            {"images": image},
            format='multipart'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class FeaturedAndNewArrivalsTests(ProductTestBase):

    def test_featured_products(self):
        """Featured endpoint returns only featured products"""
        res = self.client.get('/api/products/featured/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

    def test_non_featured_not_in_featured(self):
        """Non-featured products not in featured list"""
        self.product.is_featured = False
        self.product.save()
        res = self.client.get('/api/products/featured/')
        self.assertEqual(len(res.data), 0)

    def test_new_arrivals(self):
        """New arrivals returns recently added products"""
        res = self.client.get('/api/products/new-arrivals/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

    def test_old_products_not_in_new_arrivals(self):
        """Products older than 30 days not in new arrivals"""
        from django.utils import timezone
        from datetime import timedelta
        Product.objects.filter(id=self.product.id).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        res = self.client.get('/api/products/new-arrivals/')
        self.assertEqual(len(res.data), 0)