from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import MeView, RegisterView, CompanyUserListView, CompanyUserDetailView


urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", TokenObtainPairView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("company-users/", CompanyUserListView.as_view(), name="company-users",),
    path("company-users/<int:pk>/", CompanyUserDetailView.as_view(), name="company-user-detail",
),
]