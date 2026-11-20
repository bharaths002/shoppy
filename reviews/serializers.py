from rest_framework import serializers
from .models import Review


class ReviewUserSerializer(serializers.Serializer):
    """Lightweight user info shown on each review"""
    id = serializers.IntegerField()
    email = serializers.EmailField()


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.SerializerMethodField()
    helpful_count = serializers.SerializerMethodField()
    marked_helpful_by_me = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_slug = serializers.CharField(source='product.slug', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'reviewer_name', 'is_mine', 'product_name', 'product_slug',
            'rating', 'title', 'body', 'is_verified_purchase',
            'helpful_count', 'marked_helpful_by_me', 'created_at', 'updated_at'
        ]

    def get_reviewer_name(self, obj) -> str:
        user = obj.user
        first = (user.first_name or '').strip()
        last = (user.last_name or '').strip()
        if first:
            return f"{first} {last[0]}." if last else first
        # no name saved: show only the start of the email, never the whole address
        contact = user.email or user.phone_number or ''
        return f"{contact[:2]}***" if contact else 'Customer'

    def get_helpful_count(self, obj) -> int:
        return len(obj.helpful_votes.all())  # uses the prefetched votes, no extra query

    def get_marked_helpful_by_me(self, obj) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return any(v.user_id == request.user.id for v in obj.helpful_votes.all())
        return False

    def get_is_mine(self, obj) -> bool:
        request = self.context.get('request')
        return bool(request and request.user.is_authenticated and obj.user_id == request.user.id)


class CreateReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['rating', 'title', 'body']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_body(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Review must be at least 10 characters."
            )
        return value


class UpdateReviewSerializer(CreateReviewSerializer):
    """Same rules as creating; the view passes partial=True, so every field is optional."""
    class Meta:
        model = Review
        fields = ['rating', 'title', 'body']
        extra_kwargs = {
            'rating': {'required': False},
            'title': {'required': False},
            'body': {'required': False},
        }


class ProductRatingSummarySerializer(serializers.Serializer):
    """Summary stats shown at top of product reviews section"""
    total_reviews = serializers.IntegerField()
    average_rating = serializers.FloatField()
    five_star = serializers.IntegerField()
    four_star = serializers.IntegerField()
    three_star = serializers.IntegerField()
    two_star = serializers.IntegerField()
    one_star = serializers.IntegerField()