from rest_framework import serializers
from .models import Address


class SendOTPSerializer(serializers.Serializer):
    contact = serializers.CharField()

class VerifyOTPSerializer(serializers.Serializer):
    contact = serializers.CharField()
    otp = serializers.CharField(max_length=6)


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'id', 'full_name', 'phone_number',
            'address_line_1', 'address_line_2',
            'city', 'state', 'postal_code', 'country',
            'address_type', 'is_default', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CreateAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'full_name', 'phone_number',
            'address_line_1', 'address_line_2',
            'city', 'state', 'postal_code', 'country',
            'address_type', 'is_default'
        ]

    def validate_phone_number(self, value):
        cleaned = value.strip().replace(' ', '').replace('-', '')
        if not cleaned.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits.")
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise serializers.ValidationError("Phone number must be between 10 and 15 digits.")
        return cleaned

    def validate_postal_code(self, value):
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise serializers.ValidationError("Postal code must contain only digits.")
        if len(cleaned) != 6:
            raise serializers.ValidationError("Postal code must be 6 digits.")
        return cleaned

    def validate_full_name(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Full name must be at least 3 characters.")
        return value.strip()


class UpdateAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'full_name', 'phone_number',
            'address_line_1', 'address_line_2',
            'city', 'state', 'postal_code', 'country',
            'address_type', 'is_default'
        ]
        # All fields optional for partial update
        extra_kwargs = {f: {'required': False} for f in fields}

    def validate_phone_number(self, value):
        cleaned = value.strip().replace(' ', '').replace('-', '')
        if not cleaned.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits.")
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise serializers.ValidationError("Phone number must be between 10 and 15 digits.")
        return cleaned

    def validate_postal_code(self, value):
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise serializers.ValidationError("Postal code must contain only digits.")
        if len(cleaned) != 6:
            raise serializers.ValidationError("Postal code must be 6 digits.")
        return cleaned    