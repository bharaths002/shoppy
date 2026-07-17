
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg, Count
from .models import Review, ReviewHelpful
from .serializers import (
    ReviewSerializer, CreateReviewSerializer,
    UpdateReviewSerializer, ProductRatingSummarySerializer
)
from .utils import has_purchased_product
from products.models import Product


class ProductReviewListView(APIView):
    """
    GET  /api/reviews/<product_slug>/         → list all reviews for a product
    POST /api/reviews/<product_slug>/         → submit a review (purchased users only)
    """

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return []

    @extend_schema(
        summary="List reviews for a product",
        description="Public. Returns all active reviews for a product with rating summary.",
        parameters=[
            OpenApiParameter(
                name='ordering',
                type=OpenApiTypes.STR,
                required=False,
                description='newest | highest_rated | lowest_rated | most_helpful'
            ),
            OpenApiParameter(
                name='rating',
                type=OpenApiTypes.INT,
                required=False,
                description='Filter by star rating (1-5)'
            ),
        ],
        responses={200: inline_serializer(
            name='ProductReviewListResponse',
            fields={
                'summary': ProductRatingSummarySerializer(),
                'reviews': ReviewSerializer(many=True),
            }
        )},
        tags=["Reviews"]
    )
    def get(self, request, product_slug):
        try:
            product = Product.objects.get(slug=product_slug, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        reviews = Review.objects.filter(
            product=product, is_active=True
        ).select_related('user').prefetch_related('helpful_votes')

        # Filter by star rating
        rating_filter = request.query_params.get('rating')
        if rating_filter:
            reviews = reviews.filter(rating=rating_filter)

        # Ordering
        ordering = request.query_params.get('ordering', 'newest')
        ordering_map = {
            'newest': '-created_at',
            'highest_rated': '-rating',
            'lowest_rated': 'rating',
            'most_helpful': '-helpful_votes__count',
        }
        if ordering == 'most_helpful':
            reviews = reviews.annotate(
                helpful_count=Count('helpful_votes')
            ).order_by('-helpful_count')
        else:
            reviews = reviews.order_by(ordering_map.get(ordering, '-created_at'))

        # Rating summary
        all_reviews = Review.objects.filter(product=product, is_active=True)
        total = all_reviews.count()
        avg = all_reviews.aggregate(Avg('rating'))['rating__avg'] or 0

        summary = {
            'total_reviews': total,
            'average_rating': round(avg, 1),
            'five_star': all_reviews.filter(rating=5).count(),
            'four_star': all_reviews.filter(rating=4).count(),
            'three_star': all_reviews.filter(rating=3).count(),
            'two_star': all_reviews.filter(rating=2).count(),
            'one_star': all_reviews.filter(rating=1).count(),
        }

        serializer = ReviewSerializer(
            reviews, many=True, context={'request': request}
        )
        return Response({
            'summary': summary,
            'reviews': serializer.data
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Submit a review",
        description="""
        Authenticated users only. User must have a delivered order containing this product.
        One review per user per product. Returns 403 if not a verified purchaser.
        """,
        request=CreateReviewSerializer,
        responses={
            201: ReviewSerializer,
            400: inline_serializer(
                name='CreateReviewErrorResponse',
                fields={'error': serializers.CharField()}
            ),
            403: inline_serializer(
                name='CreateReviewForbiddenResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Reviews"]
    )
    def post(self, request, product_slug):
        try:
            product = Product.objects.get(slug=product_slug, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ✅ Verified purchase check
        if not has_purchased_product(request.user, product):
            return Response(
                {"error": "You can only review products you have purchased and received."},
                status=status.HTTP_403_FORBIDDEN
            )

        # One review per user per product
        if Review.objects.filter(user=request.user, product=product).exists():
            return Response(
                {"error": "You have already reviewed this product. Edit your existing review instead."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CreateReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        review = Review.objects.create(
            user=request.user,
            product=product,
            is_verified_purchase=True,
            **serializer.validated_data
        )

        return Response(
            ReviewSerializer(review, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class ReviewDetailView(APIView):
    """
    PATCH  /api/reviews/<product_slug>/<review_id>/  → edit own review
    DELETE /api/reviews/<product_slug>/<review_id>/  → delete own review
    """
    permission_classes = [IsAuthenticated]

    def get_review(self, review_id, user):
        try:
            return Review.objects.get(id=review_id, user=user, is_active=True)
        except Review.DoesNotExist:
            return None

    @extend_schema(
        summary="Edit your review",
        description="Update your own review. All fields optional — only send what you want to change.",
        request=UpdateReviewSerializer,
        responses={
            200: ReviewSerializer,
            404: inline_serializer(
                name='ReviewEditNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Reviews"]
    )
    def patch(self, request, product_slug, review_id):
        review = self.get_review(review_id, request.user)
        if not review:
            return Response(
                {"error": "Review not found or you don't have permission to edit it."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UpdateReviewSerializer(
            review, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(
            ReviewSerializer(review, context={'request': request}).data,
            status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Delete your review",
        description="Soft deletes your review. Sets is_active=False so it disappears from public listing.",
        responses={
            200: inline_serializer(
                name='ReviewDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
            404: inline_serializer(
                name='ReviewDeleteNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Reviews"]
    )
    def delete(self, request, product_slug, review_id):
        review = self.get_review(review_id, request.user)
        if not review:
            return Response(
                {"error": "Review not found or you don't have permission to delete it."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Soft delete
        review.is_active = False
        review.save()
        return Response(
            {"message": "Review deleted successfully."},
            status=status.HTTP_200_OK
        )


class MarkReviewHelpfulView(APIView):
    """
    POST   /api/reviews/<review_id>/helpful/  → mark review as helpful
    DELETE /api/reviews/<review_id>/helpful/  → unmark review as helpful
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mark review as helpful",
        description="Toggle helpful on a review. Cannot mark your own review as helpful.",
        responses={
            200: inline_serializer(
                name='MarkHelpfulResponse',
                fields={
                    'message': serializers.CharField(),
                    'helpful_count': serializers.IntegerField(),
                }
            ),
            400: inline_serializer(
                name='MarkHelpfulErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Reviews"]
    )
    def post(self, request, review_id):
        try:
            review = Review.objects.get(id=review_id, is_active=True)
        except Review.DoesNotExist:
            return Response(
                {"error": "Review not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Cannot mark your own review
        if review.user == request.user:
            return Response(
                {"error": "You cannot mark your own review as helpful."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Already marked — idempotent, just return current count
        if ReviewHelpful.objects.filter(review=review, user=request.user).exists():
            return Response(
                {
                    "message": "Already marked as helpful.",
                    "helpful_count": review.helpful_votes.count()
                },
                status=status.HTTP_200_OK
            )

        ReviewHelpful.objects.create(review=review, user=request.user)
        return Response(
            {
                "message": "Marked as helpful.",
                "helpful_count": review.helpful_votes.count()
            },
            status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Unmark review as helpful",
        description="Remove your helpful vote from a review.",
        responses={
            200: inline_serializer(
                name='UnmarkHelpfulResponse',
                fields={
                    'message': serializers.CharField(),
                    'helpful_count': serializers.IntegerField(),
                }
            ),
        },
        tags=["Reviews"]
    )
    def delete(self, request, review_id):
        try:
            helpful = ReviewHelpful.objects.get(
                review_id=review_id, user=request.user
            )
            helpful.delete()
            review = Review.objects.get(id=review_id)
            return Response(
                {
                    "message": "Helpful vote removed.",
                    "helpful_count": review.helpful_votes.count()
                },
                status=status.HTTP_200_OK
            )
        except ReviewHelpful.DoesNotExist:
            return Response(
                {"error": "You have not marked this review as helpful."},
                status=status.HTTP_400_BAD_REQUEST
            )


class MyReviewsView(APIView):
    """
    GET /api/reviews/my-reviews/  → all reviews written by the logged-in user
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get my reviews",
        description="Returns all reviews written by the currently logged-in user.",
        responses={200: ReviewSerializer(many=True)},
        tags=["Reviews"]
    )
    def get(self, request):
        reviews = Review.objects.filter(
            user=request.user, is_active=True
        ).select_related('product').prefetch_related('helpful_votes')
        serializer = ReviewSerializer(reviews, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminReviewManageView(APIView):
    """
    GET    /api/reviews/admin/all/           → list all reviews (with filters)
    DELETE /api/reviews/admin/<review_id>/   → hard delete a review
    """
    from products.permissions import IsAdminOrStaff
    permission_classes = [IsAdminOrStaff]

    @extend_schema(
        summary="Admin — list all reviews",
        description="Admin only. List all reviews. Filter by product slug or rating.",
        parameters=[
            OpenApiParameter(name='product_slug', type=OpenApiTypes.STR, required=False),
            OpenApiParameter(name='rating', type=OpenApiTypes.INT, required=False),
            OpenApiParameter(name='is_active', type=OpenApiTypes.BOOL, required=False),
        ],
        responses={200: ReviewSerializer(many=True)},
        tags=["Admin — Reviews"]
    )
    def get(self, request):
        reviews = Review.objects.all().select_related(
            'user', 'product'
        ).prefetch_related('helpful_votes')

        product_slug = request.query_params.get('product_slug')
        if product_slug:
            reviews = reviews.filter(product__slug=product_slug)

        rating = request.query_params.get('rating')
        if rating:
            reviews = reviews.filter(rating=rating)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            reviews = reviews.filter(is_active=is_active.lower() == 'true')

        serializer = ReviewSerializer(reviews, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Admin — delete a review",
        description="Admin only. Hard deletes a review permanently.",
        responses={
            200: inline_serializer(
                name='AdminReviewDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
            404: inline_serializer(
                name='AdminReviewDeleteNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Admin — Reviews"]
    )
    def delete(self, request, review_id):
        try:
            review = Review.objects.get(id=review_id)
            review.delete()
            return Response(
                {"message": "Review permanently deleted."},
                status=status.HTTP_200_OK
            )
        except Review.DoesNotExist:
            return Response(
                {"error": "Review not found."},
                status=status.HTTP_404_NOT_FOUND
            )