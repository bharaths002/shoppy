import secrets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import OTP, OTPRequestLog,Address
from django.contrib.auth import get_user_model, authenticate
from django.core.mail import send_mail, BadHeaderError
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from django_ratelimit.core import is_ratelimited
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from cart.utils import merge_guest_cart_to_user
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from .serializers import AddressSerializer, CreateAddressSerializer, UpdateAddressSerializer
from vendors.views import get_user_role_data




User = get_user_model()


def ratelimit_exceeded(request, exception=None):
    return JsonResponse(
        {"error": "Too many requests. Please try again later."},
        status=429
    )



class SendOTPView(APIView):
    @extend_schema(
        summary="Send OTP",
        request=inline_serializer(
            name='SendOTPRequest',
            fields={
                'email': serializers.EmailField(required=False),
                'phone': serializers.CharField(required=False),
            }
        ),
        tags=["Authentication"]
    )
    def post(self, request):

        limited = is_ratelimited(
            request,
            group='send_otp',
            key='ip',
            rate='5/10m',
            method='POST',
            increment=True
        )
        if limited:
            return Response(
                {"error": "Too many requests from your device. Please try again after 10 minutes."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        email = request.data.get("email")
        phone = request.data.get("phone")

        if not email and not phone:
            return Response(
                {"error": "Email or phone required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        contact = email if email else phone

        # Layer 2: Per-contact DB-level rate limiting (max 3 OTPs per 10 minutes)
        recent_requests = OTPRequestLog.objects.filter(
            contact=contact,
            created_at__gte=timezone.now() - timedelta(minutes=10)
        ).count()

        if recent_requests >= 3:
            return Response(
                {"error": "Too many OTP requests. Please wait 10 minutes before trying again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        lookup = {"email": email} if email else {"phone_number": phone}
        user_exists = User.objects.filter(**lookup).exists()

        # Layer 3: 15-second resend cooldown
        existing = OTP.objects.filter(contact=contact).order_by('-created_at').first()
        if existing and not existing.can_resend():
            return Response(
                {"error": "Wait 15 seconds before requesting a new OTP."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        otp = str(secrets.randbelow(900000) + 100000)

        OTP.objects.filter(contact=contact).delete()
        OTP.objects.create(contact=contact, otp=otp)

        # Log this request for Layer 2 tracking
        OTPRequestLog.objects.create(contact=contact)

        if email:
            try:
                send_mail(
                    subject="Your OTP Code",
                    message=f"Your OTP is {otp}. It is valid for 5 minutes.",
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except BadHeaderError:
                return Response(
                    {"error": "Invalid email header."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception:
                return Response(
                    {"error": "Failed to send OTP email. Please try again."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # TODO: SMS integration for phone

        return Response(
            {"message": "OTP sent. Please login." if user_exists else "OTP sent. Please register."},
            status=status.HTTP_200_OK
        )


class VerifyOTPView(APIView):

    @extend_schema(
        summary="Verify OTP",
        request=inline_serializer(
            name='VerifyOTPRequest',
            fields={
                'email': serializers.EmailField(required=False),
                'phone': serializers.CharField(required=False),
                'otp': serializers.CharField(required=True),
            }
        ),
        tags=["Authentication"]
    )

    def post(self, request):
        email = request.data.get("email")
        phone = request.data.get("phone")
        otp_input = request.data.get("otp")

        if not otp_input or (not email and not phone):
            return Response(
                {"error": "Missing required fields"},
                status=status.HTTP_400_BAD_REQUEST
            )

        contact = email if email else phone

        otp_obj = OTP.objects.filter(
            contact=contact, is_verified=False
        ).order_by('-created_at').first()

        if not otp_obj:
            return Response(
                {"error": "OTP not found. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_obj.attempts >= 5:
            otp_obj.delete()
            return Response(
                {"error": "Too many failed attempts. Please request a new OTP."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_obj.is_expired():
            otp_obj.delete()
            return Response(
                {"error": "OTP has expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_obj.otp != otp_input:
            otp_obj.attempts += 1
            otp_obj.save()
            remaining = 5 - otp_obj.attempts
            return Response(
                {"error": f"Invalid OTP. {remaining} attempt(s) remaining."},
                status=status.HTTP_400_BAD_REQUEST
            )

        otp_obj.is_verified = True
        otp_obj.save()

        lookup = {"email": email} if email else {"phone_number": phone}
        user = User.objects.filter(**lookup).first()

        if not user:
            user = User.objects.create(
                email=email if email else None,
                phone_number=phone if phone else None,
                username=(email or phone).split("@")[0] + str(secrets.randbelow(9999))
            )
            user.set_unusable_password()
            user.save()
            message = "Registered successfully."
        else:
            message = "Login successful."

        user.is_verified = True
        user.save()
        merge_guest_cart_to_user(request, user)


        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": message,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                **get_user_role_data(user)
            },
            status=status.HTTP_200_OK
        )


#  Email + Password login
class EmailPasswordLoginView(APIView):

    @extend_schema(
        summary="Login with email and password",
        request=inline_serializer(
            name='LoginRequest',
            fields={
                'email': serializers.EmailField(required=True),
                'password': serializers.CharField(required=True),
            }
        ),
        tags=["Authentication"]
    )    
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        # Validate input
        if not email or not password:
            return Response(
                {"error": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user exists first — give clear message
        user = User.objects.filter(email=email).first()
        if not user:
            return Response(
                {"error": "No account found with this email."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user has a password set
        # (OTP-only users won't have a password)
        if not user.has_usable_password():
            return Response(
                {"error": "This account uses OTP login. Please use OTP to sign in."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Authenticate
        authenticated_user = authenticate(request, username=email, password=password)
        if not authenticated_user:
            return Response(
                {"error": "Incorrect password."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(authenticated_user)

        return Response(
            {
                "message": "Login successful.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                **get_user_role_data(authenticated_user),  # ✅ adds role + vendor_profile

            },
            status=status.HTTP_200_OK
        )  




class SetPasswordView(APIView):
    
    permission_classes = [IsAuthenticated]  # must be logged in

    @extend_schema(
        summary="Set password for logged-in user",
        request=inline_serializer(
            name='SetPasswordRequest',
            fields={
                'password': serializers.CharField(required=True),
                'confirm_password': serializers.CharField(required=True),
            }
        ),
        tags=["Authentication"]
    )

    def post(self, request):
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")

        if not password or not confirm_password:
            return Response(
                {"error": "Both password fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if password != confirm_password:
            return Response(
                {"error": "Passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(password) < 8:
            return Response(
                {"error": "Password must be at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        request.user.set_password(password)
        request.user.save()

        return Response(
            {"message": "Password set successfully. You can now login with email and password."},
            status=status.HTTP_200_OK
        )          
    



class AddressListCreateView(APIView):
    """
    GET  /api/accounts/addresses/   → list all addresses for logged-in user
    POST /api/accounts/addresses/   → add a new address
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List all my addresses",
        description="Returns all saved addresses for the currently logged-in user.",
        responses={200: AddressSerializer(many=True)},
        tags=["Addresses"]
    )
    def get(self, request):
        addresses = Address.objects.filter(
            user=request.user
        ).order_by('-is_default', '-created_at')
        serializer = AddressSerializer(addresses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Add a new address",
        description="""
        Add a new shipping or billing address.
        If is_default is true, all other addresses for this user are automatically
        set to is_default=false.
        address_type choices: shipping | billing | both
        """,
        request=CreateAddressSerializer,
        responses={
            201: AddressSerializer,
            400: inline_serializer(
                name='AddressCreateErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Addresses"]
    )
    def post(self, request):
        # Max 10 addresses per user — industry standard limit
        existing_count = Address.objects.filter(user=request.user).count()
        if existing_count >= 10:
            return Response(
                {"error": "You can save a maximum of 10 addresses."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CreateAddressSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # If this is the first address, auto-set as default
        if existing_count == 0:
            address = serializer.save(user=request.user, is_default=True)
        else:
            address = serializer.save(user=request.user)

        return Response(
            AddressSerializer(address).data,
            status=status.HTTP_201_CREATED
        )


class AddressDetailView(APIView):
    """
    GET    /api/accounts/addresses/<id>/   → view single address
    PATCH  /api/accounts/addresses/<id>/   → update address
    DELETE /api/accounts/addresses/<id>/   → delete address
    """
    permission_classes = [IsAuthenticated]

    def get_address(self, address_id, user):
        try:
            return Address.objects.get(id=address_id, user=user)
        except Address.DoesNotExist:
            return None

    @extend_schema(
        summary="Get a single address",
        description="Returns details of a specific address belonging to the logged-in user.",
        responses={
            200: AddressSerializer,
            404: inline_serializer(
                name='AddressGetNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Addresses"]
    )
    def get(self, request, address_id):
        address = self.get_address(address_id, request.user)
        if not address:
            return Response(
                {"error": "Address not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = AddressSerializer(address)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update an address",
        description="Partial update — only send the fields you want to change.",
        request=UpdateAddressSerializer,
        responses={
            200: AddressSerializer,
            404: inline_serializer(
                name='AddressUpdateNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Addresses"]
    )
    def patch(self, request, address_id):
        address = self.get_address(address_id, request.user)
        if not address:
            return Response(
                {"error": "Address not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UpdateAddressSerializer(
            address, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(
            AddressSerializer(address).data,
            status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Delete an address",
        description="""
        Deletes the address permanently.
        If the deleted address was the default, the most recently added
        remaining address is automatically set as the new default.
        """,
        responses={
            200: inline_serializer(
                name='AddressDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
            400: inline_serializer(
                name='AddressDeleteErrorResponse',
                fields={'error': serializers.CharField()}
            ),
            404: inline_serializer(
                name='AddressDeleteNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Addresses"]
    )
    def delete(self, request, address_id):
        address = self.get_address(address_id, request.user)
        if not address:
            return Response(
                {"error": "Address not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        was_default = address.is_default
        address.delete()

        # If deleted address was default → auto-assign default to next address
        if was_default:
            next_address = Address.objects.filter(
                user=request.user
            ).order_by('-created_at').first()
            if next_address:
                next_address.is_default = True
                next_address.save()

        return Response(
            {"message": "Address deleted successfully."},
            status=status.HTTP_200_OK
        )


class SetDefaultAddressView(APIView):
    """
    POST /api/accounts/addresses/<id>/set-default/
    Sets one address as default and unsets all others
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Set address as default",
        description="""
        Marks the specified address as default.
        All other addresses for this user are automatically unset.
        """,
        request=None,
        responses={
            200: AddressSerializer,
            404: inline_serializer(
                name='SetDefaultNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Addresses"]
    )
    def post(self, request, address_id):
        address = Address.objects.filter(
            id=address_id, user=request.user
        ).first()
        if not address:
            return Response(
                {"error": "Address not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Unset all other defaults
        Address.objects.filter(
            user=request.user, is_default=True
        ).exclude(id=address_id).update(is_default=False)

        address.is_default = True
        address.save()

        return Response(
            AddressSerializer(address).data,
            status=status.HTTP_200_OK
        )    