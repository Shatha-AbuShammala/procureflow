from rest_framework.routers import DefaultRouter

from .views import PurchaseRequestViewSet


router = DefaultRouter()

router.register(
    "purchase-requests",
    PurchaseRequestViewSet,
    basename="purchase-request",
)

urlpatterns = router.urls