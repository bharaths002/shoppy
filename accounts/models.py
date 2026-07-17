from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.conf import settings
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, email=None, phone_number=None, password=None, **extra_fields):
        if not email and not phone_number:
            raise ValueError("Email or phone number is required")
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email, phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email=None, phone_number=None, password=None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(
            email=email, phone_number=phone_number, password=password, **extra_fields
        )


class User(AbstractUser):
    email = models.EmailField(unique=True, null=True, blank=True)

    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)

    # optional override username
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)

    is_verified = models.BooleanField(default=False)

        # ✅ New — role field to distinguish user types
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('vendor', 'Vendor'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='customer')

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email or self.phone_number or self.username or "User"

    @property
    def is_vendor(self):
        return self.role == 'vendor'

    @property
    def is_customer(self):
        return self.role == 'customer'



class OTP(models.Model):
    contact = models.CharField(max_length=100)  # phone or email
    otp = models.CharField(max_length=6)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=5)

    def can_resend(self):
        return timezone.now() > self.created_at + timezone.timedelta(seconds=15)

    def __str__(self):
        return f"{self.contact} - {self.otp}"


# ✅ New model — tracks every OTP request separately for rate limiting
class OTPRequestLog(models.Model):
    contact = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.contact} - {self.created_at}"


class Address(models.Model):
    ADDRESS_TYPE_CHOICES = (
        ("shipping", "Shipping"),
        ("billing", "Billing"),
        ("both", "Both"),
    )

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="addresses"
    )
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=15)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default="India")
    address_type = models.CharField(
        max_length=10, choices=ADDRESS_TYPE_CHOICES, default="both"
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(
                id=self.id
            ).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} — {self.city}, {self.state}"
    



class VendorProfile(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    )

    BUSINESS_TYPE_CHOICES = (
        ('individual', 'Individual / Sole Proprietor'),
        ('partnership', 'Partnership'),
        ('private_limited', 'Private Limited Company'),
        ('public_limited', 'Public Limited Company'),
    )

    # ✅ OneToOne — one vendor profile per user
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vendor_profile'
    )

    # Shop info
    shop_name = models.CharField(max_length=200)
    shop_slug = models.SlugField(max_length=200, unique=True, blank=True)
    shop_description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='vendors/logos/', null=True, blank=True)
    banner = models.ImageField(upload_to='vendors/banners/', null=True, blank=True)

    # Business info
    business_type = models.CharField(
        max_length=20, choices=BUSINESS_TYPE_CHOICES, default='individual'
    )
    gstin = models.CharField(
        max_length=15, blank=True,
        help_text="15-character GST Identification Number"
    )
    pan_number = models.CharField(max_length=10, blank=True)

    # Contact
    business_phone = models.CharField(max_length=15)
    business_email = models.EmailField()
    business_address = models.TextField(blank=True)

    # Platform settings
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True)

    # ✅ Commission rate — your platform's cut per sale
    # Industry standard: 5-20% depending on category
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        help_text="Platform commission percentage per sale"
    )

    # Metadata
    is_active = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_vendors'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-generate slug from shop name
        if not self.shop_slug:
            from django.utils.text import slugify
            import secrets
            base_slug = slugify(self.shop_name)
            self.shop_slug = f"{base_slug}-{secrets.token_hex(3)}"
        super().save(*args, **kwargs)

    @property
    def total_products(self):
        return self.products.filter(is_active=True).count()

    @property
    def is_approved(self):
        return self.status == 'approved'

    def __str__(self):
        return f"{self.shop_name} ({self.status})"

    class Meta:
        ordering = ['-created_at']    
