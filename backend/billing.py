"""Billing module — Plans (admin) + Subscriptions via Stripe / Razorpay / PayPal."""
from __future__ import annotations

import hmac
import hashlib
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("wa9x.billing")

# Optional SDKs — only required when keys are configured
try:
    import stripe as _stripe
except ImportError:
    _stripe = None

try:
    import razorpay as _razorpay
except ImportError:
    _razorpay = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------------- Pydantic models ----------------
class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price: float = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    quota_monthly: int = Field(ge=0)
    max_sessions: int = Field(default=1, ge=1)
    features: List[str] = Field(default_factory=list)
    active: bool = True
    sort: int = 0


class PlanUpdateIn(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    quota_monthly: Optional[int] = None
    max_sessions: Optional[int] = None
    features: Optional[List[str]] = None
    active: Optional[bool] = None
    sort: Optional[int] = None


class CheckoutIn(BaseModel):
    plan_id: str


# ---------------- Frontend URL helper ----------------
def frontend_url() -> str:
    return (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("BACKEND_PUBLIC_URL")
        or os.environ.get("APP_URL")
        or "http://localhost:3000"
    ).rstrip("/")


def backend_url() -> str:
    return (
        os.environ.get("BACKEND_PUBLIC_URL")
        or os.environ.get("APP_URL")
        or "http://localhost:8001"
    ).rstrip("/")


# ---------------- Stripe ----------------
def stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def stripe_init():
    if _stripe is None:
        raise HTTPException(status_code=500, detail="stripe SDK not installed")
    if not stripe_configured():
        raise HTTPException(
            status_code=400,
            detail="Stripe is not configured. Admin must set STRIPE_SECRET_KEY.",
        )
    _stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return _stripe


async def ensure_stripe_price(db, plan: dict) -> str:
    """Create Stripe Product+Price the first time (recurring monthly)."""
    stripe = stripe_init()
    if plan.get("stripe_price_id"):
        return plan["stripe_price_id"]
    product = stripe.Product.create(
        name=plan["name"],
        description=f"{plan.get('quota_monthly', 0)} messages/month",
        metadata={"plan_id": plan["id"], "quota_monthly": plan.get("quota_monthly", 0)},
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=int(round(plan["price"] * 100)),
        currency=str(plan.get("currency", "INR")).lower(),
        recurring={"interval": "month", "interval_count": 1},
        metadata={"plan_id": plan["id"]},
    )
    await db.plans.update_one(
        {"id": plan["id"]},
        {"$set": {"stripe_product_id": product.id, "stripe_price_id": price.id}},
    )
    return price.id


# ---------------- Razorpay ----------------
def razorpay_configured() -> bool:
    return bool(
        os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET")
    )


def razorpay_client():
    if _razorpay is None:
        raise HTTPException(status_code=500, detail="razorpay SDK not installed")
    if not razorpay_configured():
        raise HTTPException(
            status_code=400,
            detail="Razorpay is not configured. Admin must set RAZORPAY_KEY_ID/SECRET.",
        )
    return _razorpay.Client(
        auth=(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
    )


async def ensure_razorpay_plan(db, plan: dict) -> str:
    if plan.get("razorpay_plan_id"):
        return plan["razorpay_plan_id"]
    rp = razorpay_client()
    rp_plan = rp.plan.create(
        {
            "period": "monthly",
            "interval": 1,
            "item": {
                "name": plan["name"],
                "amount": int(round(plan["price"] * 100)),
                "currency": str(plan.get("currency", "INR")).upper(),
                "description": f"{plan.get('quota_monthly', 0)} messages/month",
            },
            "notes": {"plan_id": plan["id"]},
        }
    )
    await db.plans.update_one(
        {"id": plan["id"]}, {"$set": {"razorpay_plan_id": rp_plan["id"]}}
    )
    return rp_plan["id"]


# ---------------- PayPal (REST API v2 via httpx) ----------------
def paypal_configured() -> bool:
    return bool(
        os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_SECRET")
    )


def paypal_base() -> str:
    mode = os.environ.get("PAYPAL_MODE", "sandbox")
    return (
        "https://api-m.paypal.com"
        if mode == "live"
        else "https://api-m.sandbox.paypal.com"
    )


async def paypal_token() -> str:
    if not paypal_configured():
        raise HTTPException(
            status_code=400,
            detail="PayPal is not configured. Admin must set PAYPAL_CLIENT_ID/SECRET.",
        )
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(
            f"{paypal_base()}/v1/oauth2/token",
            auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_SECRET"]),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def ensure_paypal_plan(db, plan: dict) -> str:
    if plan.get("paypal_plan_id"):
        return plan["paypal_plan_id"]
    token = await paypal_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=20.0) as c:
        # 1. create product
        prod_r = await c.post(
            f"{paypal_base()}/v1/catalogs/products",
            headers=headers,
            json={
                "name": plan["name"],
                "description": f"{plan.get('quota_monthly', 0)} messages/month",
                "type": "SERVICE",
                "category": "SOFTWARE",
            },
        )
        prod_r.raise_for_status()
        product_id = prod_r.json()["id"]

        # 2. create plan
        plan_r = await c.post(
            f"{paypal_base()}/v1/billing/plans",
            headers=headers,
            json={
                "product_id": product_id,
                "name": plan["name"],
                "description": plan["name"],
                "billing_cycles": [
                    {
                        "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                        "tenure_type": "REGULAR",
                        "sequence": 1,
                        "total_cycles": 0,
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": str(plan["price"]),
                                "currency_code": str(
                                    plan.get("currency", "USD")
                                ).upper(),
                            }
                        },
                    }
                ],
                "payment_preferences": {"auto_bill_outstanding": True},
            },
        )
        plan_r.raise_for_status()
        paypal_plan_id = plan_r.json()["id"]
    await db.plans.update_one(
        {"id": plan["id"]},
        {"$set": {"paypal_product_id": product_id, "paypal_plan_id": paypal_plan_id}},
    )
    return paypal_plan_id


# ---------------- Subscription state helper ----------------
async def activate_subscription(
    db,
    user_id: str,
    plan: dict,
    gateway: str,
    gateway_subscription_id: str,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
):
    period_start = period_start or datetime.now(timezone.utc)
    period_end = period_end or (datetime.now(timezone.utc) + timedelta(days=30))
    sub_doc = {
        "id": new_id(),
        "user_id": user_id,
        "plan_id": plan["id"],
        "gateway": gateway,
        "gateway_subscription_id": gateway_subscription_id,
        "status": "active",
        "current_period_start": period_start.isoformat(),
        "current_period_end": period_end.isoformat(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    # mark older subs as superseded
    await db.subscriptions.update_many(
        {"user_id": user_id, "status": "active"},
        {"$set": {"status": "superseded", "updated_at": now_iso()}},
    )
    await db.subscriptions.insert_one(sub_doc)
    await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "current_plan_id": plan["id"],
                "current_subscription_id": sub_doc["id"],
                "quota_monthly": int(plan.get("quota_monthly", 0) or 0),
                "quota_used": 0,
            }
        },
    )
    logger.info("subscription activated user=%s plan=%s gw=%s", user_id, plan["id"], gateway)
    sub_doc.pop("_id", None)
    return sub_doc


async def cancel_subscription_db(db, user_id: str, gateway: str):
    sub = await db.subscriptions.find_one(
        {"user_id": user_id, "gateway": gateway, "status": "active"}, {"_id": 0}
    )
    if not sub:
        return None
    await db.subscriptions.update_one(
        {"id": sub["id"]},
        {"$set": {"status": "cancelled", "updated_at": now_iso()}},
    )
    await db.users.update_one(
        {"id": user_id},
        {
            "$unset": {"current_plan_id": "", "current_subscription_id": ""},
            "$set": {"quota_monthly": 1000},
        },
    )
    return sub


# ---------------- Router factory ----------------
def make_router(db, current_user, admin_only):
    """Build the billing router. Imports auth deps from caller."""
    api = APIRouter()

    # =========== Public + Admin: Plans ===========
    @api.get("/plans")
    async def list_plans_public():
        cursor = db.plans.find({"active": True}, {"_id": 0}).sort("sort", 1)
        return await cursor.to_list(length=100)

    @api.get("/admin/plans")
    async def list_plans_admin(_: dict = Depends(admin_only)):
        cursor = db.plans.find({}, {"_id": 0}).sort("sort", 1)
        return await cursor.to_list(length=200)

    @api.post("/admin/plans")
    async def create_plan(payload: PlanIn, _: dict = Depends(admin_only)):
        doc = payload.model_dump()
        doc.update({"id": new_id(), "created_at": now_iso(), "updated_at": now_iso()})
        await db.plans.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @api.patch("/admin/plans/{plan_id}")
    async def update_plan(
        plan_id: str, payload: PlanUpdateIn, _: dict = Depends(admin_only)
    ):
        update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if not update:
            raise HTTPException(status_code=400, detail="No fields to update")
        update["updated_at"] = now_iso()
        result = await db.plans.update_one({"id": plan_id}, {"$set": update})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Plan not found")
        plan = await db.plans.find_one({"id": plan_id}, {"_id": 0})
        return plan

    @api.delete("/admin/plans/{plan_id}")
    async def delete_plan(plan_id: str, _: dict = Depends(admin_only)):
        result = await db.plans.delete_one({"id": plan_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Plan not found")
        return {"ok": True}

    # =========== Customer: current subscription ===========
    @api.get("/me/subscription")
    async def my_subscription(user: dict = Depends(current_user)):
        sub = await db.subscriptions.find_one(
            {"user_id": user["id"], "status": "active"}, {"_id": 0}
        )
        plan = None
        if sub:
            plan = await db.plans.find_one({"id": sub["plan_id"]}, {"_id": 0})
        return {"subscription": sub, "plan": plan}

    @api.get("/billing/gateways")
    async def gateways_status():
        return {
            "stripe": stripe_configured(),
            "razorpay": razorpay_configured(),
            "paypal": paypal_configured(),
        }

    # =========== Stripe ===========
    @api.post("/billing/stripe/checkout")
    async def stripe_checkout(payload: CheckoutIn, user: dict = Depends(current_user)):
        stripe = stripe_init()
        plan = await db.plans.find_one({"id": payload.plan_id, "active": True}, {"_id": 0})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        price_id = await ensure_stripe_price(db, plan)
        # ensure / find customer
        customer_id = user.get("stripe_customer_id")
        if not customer_id:
            customer = stripe.Customer.create(
                email=user["email"], name=user["name"], metadata={"user_id": user["id"]}
            )
            customer_id = customer.id
            await db.users.update_one(
                {"id": user["id"]}, {"$set": {"stripe_customer_id": customer_id}}
            )

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            metadata={"user_id": user["id"], "plan_id": plan["id"]},
            subscription_data={
                "metadata": {"user_id": user["id"], "plan_id": plan["id"]}
            },
            success_url=f"{frontend_url()}/app/billing?ok=stripe&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{frontend_url()}/app/billing?cancel=stripe",
        )
        return {"checkout_url": session.url}

    @api.post("/billing/stripe/cancel")
    async def stripe_cancel(user: dict = Depends(current_user)):
        stripe = stripe_init()
        sub = await db.subscriptions.find_one(
            {"user_id": user["id"], "gateway": "stripe", "status": "active"},
            {"_id": 0},
        )
        if not sub:
            raise HTTPException(status_code=404, detail="No active Stripe subscription")
        try:
            stripe.Subscription.delete(sub["gateway_subscription_id"])
        except Exception as e:
            logger.warning("stripe cancel error: %s", e)
        await cancel_subscription_db(db, user["id"], "stripe")
        return {"ok": True}

    @api.post("/webhooks/stripe")
    async def webhook_stripe(request: Request):
        if _stripe is None or not stripe_configured():
            raise HTTPException(status_code=400, detail="Stripe not configured")
        _stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        body = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            if secret:
                event = _stripe.Webhook.construct_event(body, sig, secret)
            else:
                event = json.loads(body)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid signature: {e}")

        etype = event.get("type")
        data = event.get("data", {}).get("object", {})
        if etype == "checkout.session.completed":
            md = data.get("metadata") or {}
            user_id = md.get("user_id")
            plan_id = md.get("plan_id")
            sub_id = data.get("subscription")
            if user_id and plan_id and sub_id:
                plan = await db.plans.find_one({"id": plan_id}, {"_id": 0})
                if plan:
                    await activate_subscription(db, user_id, plan, "stripe", sub_id)
        elif etype == "customer.subscription.deleted":
            sub_doc = await db.subscriptions.find_one(
                {"gateway_subscription_id": data.get("id")}, {"_id": 0}
            )
            if sub_doc:
                await cancel_subscription_db(db, sub_doc["user_id"], "stripe")
        elif etype == "invoice.payment_failed":
            await db.subscriptions.update_one(
                {"gateway_subscription_id": data.get("subscription")},
                {"$set": {"status": "past_due", "updated_at": now_iso()}},
            )
        return {"ok": True}

    # =========== Razorpay ===========
    @api.post("/billing/razorpay/create-subscription")
    async def razorpay_create(payload: CheckoutIn, user: dict = Depends(current_user)):
        rp = razorpay_client()
        plan = await db.plans.find_one({"id": payload.plan_id, "active": True}, {"_id": 0})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        rp_plan_id = await ensure_razorpay_plan(db, plan)
        try:
            sub = rp.subscription.create(
                {
                    "plan_id": rp_plan_id,
                    "customer_notify": 1,
                    "total_count": 12,
                    "notes": {"user_id": user["id"], "plan_id": plan["id"]},
                }
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "subscription_id": sub.get("id"),
            "short_url": sub.get("short_url"),
            "status": sub.get("status"),
            "key_id": os.environ.get("RAZORPAY_KEY_ID"),
        }

    @api.post("/billing/razorpay/cancel")
    async def razorpay_cancel(user: dict = Depends(current_user)):
        rp = razorpay_client()
        sub = await db.subscriptions.find_one(
            {"user_id": user["id"], "gateway": "razorpay", "status": "active"},
            {"_id": 0},
        )
        if not sub:
            raise HTTPException(status_code=404, detail="No active Razorpay subscription")
        try:
            rp.subscription.cancel(sub["gateway_subscription_id"])
        except Exception as e:
            logger.warning("razorpay cancel error: %s", e)
        await cancel_subscription_db(db, user["id"], "razorpay")
        return {"ok": True}

    @api.post("/webhooks/razorpay")
    async def webhook_razorpay(request: Request):
        secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        body = await request.body()
        sig = request.headers.get("x-razorpay-signature", "")
        if secret:
            expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise HTTPException(status_code=400, detail="invalid signature")
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")

        etype = event.get("event")
        payload = event.get("payload", {})
        if etype == "subscription.activated":
            sub = payload.get("subscription", {}).get("entity", {}) or payload.get(
                "subscription", {}
            )
            notes = sub.get("notes") or {}
            user_id = notes.get("user_id")
            plan_id = notes.get("plan_id")
            if user_id and plan_id:
                plan = await db.plans.find_one({"id": plan_id}, {"_id": 0})
                if plan:
                    await activate_subscription(
                        db, user_id, plan, "razorpay", sub.get("id", "")
                    )
        elif etype == "subscription.cancelled":
            sub = payload.get("subscription", {}).get("entity", {}) or payload.get(
                "subscription", {}
            )
            sub_doc = await db.subscriptions.find_one(
                {"gateway_subscription_id": sub.get("id")}, {"_id": 0}
            )
            if sub_doc:
                await cancel_subscription_db(db, sub_doc["user_id"], "razorpay")
        return {"ok": True}

    # =========== PayPal ===========
    @api.post("/billing/paypal/create-subscription")
    async def paypal_create(payload: CheckoutIn, user: dict = Depends(current_user)):
        plan = await db.plans.find_one({"id": payload.plan_id, "active": True}, {"_id": 0})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        pp_plan_id = await ensure_paypal_plan(db, plan)
        token = await paypal_token()
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                f"{paypal_base()}/v1/billing/subscriptions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "plan_id": pp_plan_id,
                    "subscriber": {"email_address": user["email"]},
                    "custom_id": f"{user['id']}::{plan['id']}",
                    "application_context": {
                        "brand_name": "wa.9x.design",
                        "user_action": "SUBSCRIBE_NOW",
                        "return_url": f"{backend_url()}/api/billing/paypal/return?user_id={user['id']}&plan_id={plan['id']}",
                        "cancel_url": f"{frontend_url()}/app/billing?cancel=paypal",
                    },
                },
            )
            if r.status_code >= 400:
                raise HTTPException(status_code=400, detail=r.text)
            data = r.json()
        approve = next(
            (link["href"] for link in data.get("links", []) if link.get("rel") == "approve"),
            None,
        )
        return {
            "subscription_id": data.get("id"),
            "approval_url": approve,
            "status": data.get("status"),
        }

    @api.get("/billing/paypal/return")
    async def paypal_return(
        request: Request, subscription_id: str = "", user_id: str = "", plan_id: str = ""
    ):
        # PayPal redirects with `subscription_id` query param
        sid = request.query_params.get("subscription_id") or subscription_id
        if not (user_id and plan_id and sid):
            return RedirectResponse(f"{frontend_url()}/app/billing?error=paypal-missing-params")
        token = await paypal_token()
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                f"{paypal_base()}/v1/billing/subscriptions/{sid}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code >= 400:
                return RedirectResponse(f"{frontend_url()}/app/billing?error=paypal-fetch-failed")
            data = r.json()
        if data.get("status") in ("ACTIVE", "APPROVED", "APPROVAL_PENDING"):
            plan = await db.plans.find_one({"id": plan_id}, {"_id": 0})
            if plan:
                await activate_subscription(db, user_id, plan, "paypal", sid)
        return RedirectResponse(f"{frontend_url()}/app/billing?ok=paypal")

    @api.post("/billing/paypal/cancel")
    async def paypal_cancel(user: dict = Depends(current_user)):
        sub = await db.subscriptions.find_one(
            {"user_id": user["id"], "gateway": "paypal", "status": "active"},
            {"_id": 0},
        )
        if not sub:
            raise HTTPException(status_code=404, detail="No active PayPal subscription")
        try:
            token = await paypal_token()
            async with httpx.AsyncClient(timeout=15.0) as c:
                await c.post(
                    f"{paypal_base()}/v1/billing/subscriptions/{sub['gateway_subscription_id']}/cancel",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={"reason": "user requested"},
                )
        except Exception as e:
            logger.warning("paypal cancel error: %s", e)
        await cancel_subscription_db(db, user["id"], "paypal")
        return {"ok": True}

    @api.post("/webhooks/paypal")
    async def webhook_paypal(request: Request):
        # PayPal webhook signature verification requires PAYPAL_WEBHOOK_ID
        # For MVP, parse body and react. In production, call /v1/notifications/verify-webhook-signature
        body = await request.body()
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")
        etype = event.get("event_type")
        resource = event.get("resource") or {}
        if etype in ("BILLING.SUBSCRIPTION.ACTIVATED", "BILLING.SUBSCRIPTION.CREATED"):
            sid = resource.get("id")
            custom = resource.get("custom_id", "")
            user_id, _, plan_id = custom.partition("::")
            if user_id and plan_id and sid:
                plan = await db.plans.find_one({"id": plan_id}, {"_id": 0})
                if plan:
                    await activate_subscription(db, user_id, plan, "paypal", sid)
        elif etype == "BILLING.SUBSCRIPTION.CANCELLED":
            sid = resource.get("id")
            sub_doc = await db.subscriptions.find_one(
                {"gateway_subscription_id": sid}, {"_id": 0}
            )
            if sub_doc:
                await cancel_subscription_db(db, sub_doc["user_id"], "paypal")
        return {"ok": True}

    return api
