from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from products.models import Product, Category, Brand
from orders.models import Order, OrderItem
from accounts.models import Address
from .models import Review, ReviewHelpful

User = get_user_model()


class ReviewTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.customer = User.objects.create(
            email="reviewer@test.com", username="reviewer"
        )
        self.customer2 = User.objects.create(
            email="reviewer2@test.com", username="reviewer2"
        )
        self.admin = User.objects.create(
            email="adminreview@test.com", username="adminreview",
            is_staff=True, is_superuser=True
        )

        self.category = Category.objects.create(
            name="Electronics", slug="electronics-review"
        )
        self.brand = Brand.objects.create(
            name="Samsung", slug="samsung-review"
        )
        self.product = Product.objects.create(
            name="Samsung Buds Pro",
            category=self.category,
            brand=self.brand,
            price=5999,
            stock=100,
            has_variants=False,
            is_active=True,
        )

        self.address = Address.objects.create(
            user=self.customer,
            full_name="Test",
            phone_number="9876543210",
            address_line_1="123 Street",
            city="Chennai",
            state="TN",
            postal_code="600001",
            country="India",
            address_type="both",
            is_default=True
        )

        # Create a delivered order so customer can review
        self.order = Order.objects.create(
            user=self.customer,
            shipping_address=self.address,
            billing_address=self.address,
            payment_method='cod',
            payment_status='pending',
            subtotal=5999,
            shipping_fee=0,
            total=5999,
            status='delivered'
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            unit_price=5999,
            quantity=1
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)


# ─────────────────────────────────────────────────────────────
# Review Submit Tests
# ─────────────────────────────────────────────────────────────

class SubmitReviewTests(ReviewTestBase):

    def test_verified_buyer_can_review(self):
        self.auth(self.customer)
        res = self.client.post(
            f'/api/reviews/{self.product.slug}/',
            {
                "rating": 5,
                "title": "Amazing product",
                "body": "Best earbuds I have used so far."
            },
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data['is_verified_purchase'])

    def test_non_buyer_cannot_review(self):
        self.auth(self.customer2)
        res = self.client.post(
            f'/api/reviews/{self.product.slug}/',
            {"rating": 4, "body": "Good product overall I think"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_review_fails(self):
        Review.objects.create(
            user=self.customer,
            product=self.product,
            rating=5,
            body="First review here",
            is_verified_purchase=True
        )
        self.auth(self.customer)
        res = self.client.post(
            f'/api/reviews/{self.product.slug}/',
            {"rating": 3, "body": "Second review attempt here"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already reviewed", res.data['error'])

    def test_short_body_fails(self):
        self.auth(self.customer)
        res = self.client.post(
            f'/api/reviews/{self.product.slug}/',
            {"rating": 3, "body": "ok"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_rating_fails(self):
        self.auth(self.customer)
        res = self.client.post(
            f'/api/reviews/{self.product.slug}/',
            {"rating": 6, "body": "This is a valid review body text"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_review(self):
        self.client.force_authenticate(user=None)
        res = self.client.post(
            f'/api/reviews/{self.product.slug}/',
            {"rating": 5, "body": "Great product really nice"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_review_nonexistent_product(self):
        self.auth(self.customer)
        res = self.client.post(
            '/api/reviews/nonexistent-product-slug/',
            {"rating": 5, "body": "Great product really nice"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────
# Review List Tests
# ─────────────────────────────────────────────────────────────

class ReviewListTests(ReviewTestBase):

    def setUp(self):
        super().setUp()
        self.review = Review.objects.create(
            user=self.customer,
            product=self.product,
            rating=5,
            title="Great product",
            body="Best earbuds I have ever used",
            is_verified_purchase=True
        )

    def test_public_can_list_reviews(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(f'/api/reviews/{self.product.slug}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('summary', res.data)
        self.assertIn('reviews', res.data)

    def test_summary_has_correct_counts(self):
        res = self.client.get(f'/api/reviews/{self.product.slug}/')
        summary = res.data['summary']
        self.assertEqual(summary['total_reviews'], 1)
        self.assertEqual(summary['average_rating'], 5.0)
        self.assertEqual(summary['five_star'], 1)
        self.assertEqual(summary['four_star'], 0)

    def test_filter_by_rating(self):
        Review.objects.create(
            user=self.customer2,
            product=self.product,
            rating=3,
            body="Decent product worth the money",
            is_verified_purchase=False
        )
        res = self.client.get(
            f'/api/reviews/{self.product.slug}/?rating=5'
        )
        self.assertEqual(len(res.data['reviews']), 1)
        self.assertEqual(res.data['reviews'][0]['rating'], 5)

    def test_ordering_highest_rated(self):
        Review.objects.create(
            user=self.customer2,
            product=self.product,
            rating=2,
            body="Not so good product",
            is_verified_purchase=False
        )
        res = self.client.get(
            f'/api/reviews/{self.product.slug}/?ordering=highest_rated'
        )
        ratings = [r['rating'] for r in res.data['reviews']]
        self.assertEqual(ratings, sorted(ratings, reverse=True))

    def test_my_reviews(self):
        self.auth(self.customer)
        res = self.client.get('/api/reviews/my-reviews/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)


# ─────────────────────────────────────────────────────────────
# Review Edit and Delete Tests
# ─────────────────────────────────────────────────────────────

class ReviewEditDeleteTests(ReviewTestBase):

    def setUp(self):
        super().setUp()
        self.review = Review.objects.create(
            user=self.customer,
            product=self.product,
            rating=5,
            title="Great",
            body="Best earbuds I have ever used",
            is_verified_purchase=True
        )

    def test_owner_can_edit_review(self):
        self.auth(self.customer)
        res = self.client.patch(
            f'/api/reviews/{self.product.slug}/{self.review.id}/',
            {"rating": 4, "body": "Good product but battery drains fast"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 4)

    def test_other_user_cannot_edit_review(self):
        self.auth(self.customer2)
        res = self.client.patch(
            f'/api/reviews/{self.product.slug}/{self.review.id}/',
            {"rating": 1, "body": "Trying to change someone's review"},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_delete_review(self):
        self.auth(self.customer)
        res = self.client.delete(
            f'/api/reviews/{self.product.slug}/{self.review.id}/'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_active)

    def test_other_user_cannot_delete_review(self):
        self.auth(self.customer2)
        res = self.client.delete(
            f'/api/reviews/{self.product.slug}/{self.review.id}/'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_deleted_review_not_in_listing(self):
        self.auth(self.customer)
        self.client.delete(
            f'/api/reviews/{self.product.slug}/{self.review.id}/'
        )
        res = self.client.get(f'/api/reviews/{self.product.slug}/')
        self.assertEqual(res.data['summary']['total_reviews'], 0)


# ─────────────────────────────────────────────────────────────
# Helpful Vote Tests
# ─────────────────────────────────────────────────────────────

class ReviewHelpfulTests(ReviewTestBase):

    def setUp(self):
        super().setUp()
        self.review = Review.objects.create(
            user=self.customer,
            product=self.product,
            rating=5,
            body="Best earbuds I have ever used",
            is_verified_purchase=True
        )

    def test_other_user_can_mark_helpful(self):
        self.auth(self.customer2)
        res = self.client.post(f'/api/reviews/helpful/{self.review.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['helpful_count'], 1)

    def test_cannot_mark_own_review_helpful(self):
        self.auth(self.customer)
        res = self.client.post(f'/api/reviews/helpful/{self.review.id}/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_helpful_vote_idempotent(self):
        self.auth(self.customer2)
        self.client.post(f'/api/reviews/helpful/{self.review.id}/')
        res = self.client.post(f'/api/reviews/helpful/{self.review.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['helpful_count'], 1)

    def test_unmark_helpful(self):
        self.auth(self.customer2)
        self.client.post(f'/api/reviews/helpful/{self.review.id}/')
        res = self.client.delete(f'/api/reviews/helpful/{self.review.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['helpful_count'], 0)

    def test_unmark_without_marking_fails(self):
        self.auth(self.customer2)
        res = self.client.delete(f'/api/reviews/helpful/{self.review.id}/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)