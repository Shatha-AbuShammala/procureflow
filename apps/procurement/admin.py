from django.contrib import admin

from .models import (
    Approval,
    PurchaseRequest,
    PurchaseRequestItem,
)


class PurchaseRequestItemInline(admin.TabularInline):
    model = PurchaseRequestItem
    extra = 0


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "title",
        "company",
        "requester",
        "status",
        "created_at",
    )

    list_filter = (
        "company",
        "status",
    )

    search_fields = (
        "title",
        "requester__username",
    )

    inlines = [
        PurchaseRequestItemInline,
    ]


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):

    list_display = (
        "purchase_request",
        "approver",
        "status",
        "decided_at",
    )