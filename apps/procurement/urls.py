from rest_framework.routers import DefaultRouter

from .views import (
    PurchaseRequestViewSet,
    RFQViewSet,
    SupplierQuoteViewSet,
)


router = DefaultRouter()

router.register(
    "purchase-requests",
    PurchaseRequestViewSet,
    basename="purchase-request",
)

router.register(
    "rfqs",
    RFQViewSet,
    basename="rfq",
)

router.register(
    "quotes",
    SupplierQuoteViewSet,
    basename="quote",
)


urlpatterns = router.urls