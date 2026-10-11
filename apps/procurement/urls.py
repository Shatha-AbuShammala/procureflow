from rest_framework.routers import DefaultRouter

from .views import (
    PurchaseRequestViewSet,
    RFQViewSet,
    SupplierQuoteViewSet,
    PurchaseOrderViewSet,
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
router.register(
    r"purchase-orders",
    PurchaseOrderViewSet,
    basename="purchase-order",
)

urlpatterns = router.urls