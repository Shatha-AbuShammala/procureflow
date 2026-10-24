from django.urls import path
from .views import (
    LoginView,
    RefreshView,
    MeView,
    RegisterView,
    CompanyUserListView,
    CompanyUserDetailView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path(
        "company-users/",
        CompanyUserListView.as_view(),
        name="company-users",
    ),
    path(
        "company-users/<int:pk>/",
        CompanyUserDetailView.as_view(),
        name="company-user-detail",
    ),
]
