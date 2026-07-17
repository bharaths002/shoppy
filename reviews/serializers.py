from rest_framework import serializers
from .models import Review


class ReviewUserSerializer(serializers.Serializer):
    """Lightweight user info shown on each review"""
    id = serializers.IntegerField()
    email = serializers.EmailField()


class ReviewSerializer(serializers.ModelSerializer):
    user = ReviewUserSerializer(read_only=True)
    helpful_count = serializers.SerializerMethodField()
    marked_helpful_by_me = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            'id', 'user', 'rating', 'title', 'body',
            'is_verified_purchase', 'helpful_count',
            'marked_helpful_by_me', 'created_at', 'updated_at'
        ]

    def get_helpful_count(self, obj):
        return obj.helpful_votes.count()

    def get_marked_helpful_by_me(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.helpful_votes.filter(user=request.user).exists()
        return False


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


class UpdateReviewSerializer(serializers.ModelSerializer):
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