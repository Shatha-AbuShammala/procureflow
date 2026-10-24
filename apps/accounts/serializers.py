from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.utils import get_md5_hash_password
from secrets import compare_digest

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
        )

    def validate(self, attrs):
        user = User(username=attrs.get("username", ""), email=attrs.get("email", ""))
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            if User.objects.filter(username=validated_data["username"]).exists():
                raise serializers.ValidationError(
                    {"username": "This username is already registered."}
                ) from exc
            raise


class SafeTokenRefreshSerializer(TokenRefreshSerializer):
    @transaction.atomic
    def validate(self, attrs):
        token = self.token_class(attrs["refresh"])
        # Serialize rotations so two simultaneous refreshes cannot both succeed.
        OutstandingToken.objects.select_for_update().filter(
            jti=token[api_settings.JTI_CLAIM]
        ).first()
        try:
            user = User.objects.get(pk=token[api_settings.USER_ID_CLAIM])
        except (User.DoesNotExist, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationFailed(
                "No active account found for the given token."
            ) from exc
        if not user.is_active or (
            api_settings.CHECK_REVOKE_TOKEN
            and not compare_digest(
                str(token.get(api_settings.REVOKE_TOKEN_CLAIM, "")),
                get_md5_hash_password(user.password),
            )
        ):
            raise AuthenticationFailed("No active account found for the given token.")
        return super().validate(attrs)


class CompanyUserSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(
        source="company.name",
        read_only=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "company",
            "company_name",
            "role",
        )

        read_only_fields = (
            "company",
            "role",
        )
