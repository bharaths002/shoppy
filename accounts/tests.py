
# Create your tests here.
from django.test import TestCase, override_settings
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import OTP, OTPRequestLog
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

# Use dummy cache for all tests so rate limiting is isolated
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
)
class SendOTPTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = '/api/accounts/sendotp/'
        cache.clear()

    # ── Happy Path ────────────────────────────────────────

    def test_send_otp_with_email_success(self):
        """New email gets OTP sent successfully"""
        res = self.client.post(self.url, {"email": "test@gmail.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("OTP sent", res.data["message"])
        self.assertTrue(OTP.objects.filter(contact="test@gmail.com").exists())

    def test_send_otp_new_user_message(self):
        """New user gets register message"""
        res = self.client.post(self.url, {"email": "newuser@gmail.com"})
        self.assertIn("register", res.data["message"].lower())

    def test_send_otp_existing_user_message(self):
        """Existing user gets login message"""
        User.objects.create(email="existing@gmail.com", username="existing123")
        res = self.client.post(self.url, {"email": "existing@gmail.com"})
        self.assertIn("login", res.data["message"].lower())

    def test_otp_is_6_digits(self):
        """OTP generated must be exactly 6 digits"""
        self.client.post(self.url, {"email": "test@gmail.com"})
        otp = OTP.objects.filter(contact="test@gmail.com").first()
        self.assertIsNotNone(otp)
        self.assertEqual(len(otp.otp), 6)
        self.assertTrue(otp.otp.isdigit())

    def test_old_otp_deleted_on_new_request(self):
        """Only one active OTP per contact at a time"""
        self.client.post(self.url, {"email": "test@gmail.com"})
        first_otp = OTP.objects.filter(contact="test@gmail.com").first().otp
        # wait 15 seconds virtually
        OTP.objects.filter(contact="test@gmail.com").update(
            created_at=timezone.now() - timedelta(seconds=20)
        )
        self.client.post(self.url, {"email": "test@gmail.com"})
        otps = OTP.objects.filter(contact="test@gmail.com")
        self.assertEqual(otps.count(), 1)
        self.assertNotEqual(otps.first().otp, first_otp)

    # ── Edge Cases ────────────────────────────────────────

    def test_send_otp_no_email_or_phone(self):
        """Missing both email and phone returns 400"""
        res = self.client.post(self.url, {})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", res.data)

    def test_send_otp_empty_email(self):
        """Empty string email returns 400"""
        res = self.client.post(self.url, {"email": ""})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_otp_request_log_created(self):
        """Every OTP request is logged for rate limiting"""
        self.client.post(self.url, {"email": "test@gmail.com"})
        self.assertTrue(OTPRequestLog.objects.filter(contact="test@gmail.com").exists())

    # ── Rate Limiting ─────────────────────────────────────

    def test_resend_cooldown_15_seconds(self):
        """Cannot resend OTP within 15 seconds"""
        self.client.post(self.url, {"email": "test@gmail.com"})
        res = self.client.post(self.url, {"email": "test@gmail.com"})
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("15 seconds", res.data["error"])

    def test_resend_allowed_after_15_seconds(self):
        """OTP resend is allowed after 15 seconds"""
        self.client.post(self.url, {"email": "test@gmail.com"})
        # Simulate 20 seconds passed
        OTP.objects.filter(contact="test@gmail.com").update(
            created_at=timezone.now() - timedelta(seconds=20)
        )
        res = self.client.post(self.url, {"email": "test@gmail.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_max_3_otps_per_10_minutes(self):
        """Blocked after 3 OTP requests in 10 minutes"""
        # Create 3 logs manually
        for _ in range(3):
            OTPRequestLog.objects.create(contact="test@gmail.com")
        res = self.client.post(self.url, {"email": "test@gmail.com"})
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("10 minutes", res.data["error"])

    def test_old_logs_dont_count_toward_rate_limit(self):
        """Logs older than 10 minutes don't count"""
        for _ in range(3):
            OTPRequestLog.objects.create(
                contact="test@gmail.com",
            )
        # Push logs to 11 minutes ago
        OTPRequestLog.objects.filter(contact="test@gmail.com").update(
            created_at=timezone.now() - timedelta(minutes=11)
        )
        res = self.client.post(self.url, {"email": "test@gmail.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
)
class VerifyOTPTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = '/api/accounts/verifyotp/'
        self.email = "verify@gmail.com"
        self.otp_obj = OTP.objects.create(contact=self.email, otp="123456")

    # ── Happy Path ────────────────────────────────────────

    def test_verify_otp_new_user_registers(self):
        """Valid OTP for new email creates user and returns tokens"""
        res = self.client.post(self.url, {"email": self.email, "otp": "123456"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["message"], "Registered successfully.")
        self.assertTrue(User.objects.filter(email=self.email).exists())

    def test_verify_otp_existing_user_logs_in(self):
        """Valid OTP for existing user returns login message"""
        User.objects.create(email=self.email, username="verifyuser")
        res = self.client.post(self.url, {"email": self.email, "otp": "123456"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["message"], "Login successful.")

    def test_user_is_verified_after_otp(self):
        """User is_verified flag is set to True after OTP verification"""
        self.client.post(self.url, {"email": self.email, "otp": "123456"})
        user = User.objects.get(email=self.email)
        self.assertTrue(user.is_verified)

    def test_otp_marked_verified_after_use(self):
        """OTP is_verified flag set to True after successful verify"""
        self.client.post(self.url, {"email": self.email, "otp": "123456"})
        self.otp_obj.refresh_from_db()
        self.assertTrue(self.otp_obj.is_verified)

    # ── Edge Cases ────────────────────────────────────────

    def test_verify_wrong_otp(self):
        """Wrong OTP returns 400 and decrements remaining attempts"""
        res = self.client.post(self.url, {"email": self.email, "otp": "000000"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("remaining", res.data["error"])

    def test_verify_missing_otp_field(self):
        """Missing OTP field returns 400"""
        res = self.client.post(self.url, {"email": self.email})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_missing_email_and_phone(self):
        """Missing both email and phone returns 400"""
        res = self.client.post(self.url, {"otp": "123456"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_nonexistent_otp(self):
        """OTP not in DB returns 400"""
        res = self.client.post(self.url, {"email": "ghost@gmail.com", "otp": "123456"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not found", res.data["error"])

    def test_verify_expired_otp(self):
        """Expired OTP returns 400 and deletes the OTP"""
        self.otp_obj.created_at = timezone.now() - timedelta(minutes=10)
        self.otp_obj.save()
        res = self.client.post(self.url, {"email": self.email, "otp": "123456"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", res.data["error"])
        self.assertFalse(OTP.objects.filter(contact=self.email).exists())

    # ── Security / Brute Force ────────────────────────────

    def test_brute_force_5_wrong_attempts_deletes_otp(self):
        """After 5 wrong attempts OTP is deleted"""
        self.otp_obj.attempts = 5
        self.otp_obj.save()
        res = self.client.post(self.url, {"email": self.email, "otp": "000000"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(OTP.objects.filter(contact=self.email, is_verified=False).exists())

    def test_attempts_increment_on_wrong_otp(self):
        """Attempts counter increments on each wrong OTP"""
        self.client.post(self.url, {"email": self.email, "otp": "000000"})
        self.otp_obj.refresh_from_db()
        self.assertEqual(self.otp_obj.attempts, 1)

    def test_remaining_attempts_shown_correctly(self):
        """Correct remaining attempts shown in error message"""
        res = self.client.post(self.url, {"email": self.email, "otp": "000000"})
        self.assertIn("4 attempt(s) remaining", res.data["error"])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
)
class EmailPasswordLoginTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = '/api/accounts/login/'
        self.user = User.objects.create(email="admin@gmail.com", username="admin123")
        self.user.set_password("Test@1234")
        self.user.save()

    # ── Happy Path ────────────────────────────────────────

    def test_login_success(self):
        """Valid email and password returns tokens"""
        res = self.client.post(self.url, {"email": "admin@gmail.com", "password": "Test@1234"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    # ── Edge Cases ────────────────────────────────────────

    def test_login_wrong_password(self):
        """Wrong password returns 401"""
        res = self.client.post(self.url, {"email": "admin@gmail.com", "password": "wrongpass"})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_nonexistent_email(self):
        """Email not in DB returns 404"""
        res = self.client.post(self.url, {"email": "ghost@gmail.com", "password": "Test@1234"})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_login_missing_fields(self):
        """Missing email or password returns 400"""
        res = self.client.post(self.url, {"email": "admin@gmail.com"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_otp_only_user(self):
        """OTP-only user (no password) gets.   appropriate error"""
        otp_user = User.objects.create(email="otpuser@gmail.com", username="otpuser123")
        otp_user.set_unusable_password()
        otp_user.save()
        res = self.client.post(self.url, {"email": "otpuser@gmail.com", "password": "anything"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("OTP", res.data["error"])