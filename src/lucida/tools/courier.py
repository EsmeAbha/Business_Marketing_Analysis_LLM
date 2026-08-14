"""Courier / logistics adapters: Steadfast, Pathao, and a generic ride-hail stub.

Same contract as the social adapters — real HTTP when credentials exist,
otherwise a labelled simulated consignment with realistic fields (consignment
ID, tracking code, ETA, COD amount) so the delivery flow is fully demonstrable.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.courier")

STEADFAST_BASE = "https://portal.packzy.com/api/v1"
PATHAO_BASE = "https://api-hermes.pathao.com"
_TIMEOUT = 20

SUPPORTED_PROVIDERS = ("steadfast", "pathao", "uber")


def _creds(provider: str) -> tuple[str, str]:
    """This shop's courier keys, falling back to the machine's."""
    try:
        from ..memory import memory
        from . import connections
        return connections.credentials(memory.db, provider)
    except Exception:  # noqa: BLE001 — outside a request there is no shop
        if provider == "steadfast":
            return settings.steadfast_api_key, settings.steadfast_secret_key
        if provider == "pathao":
            return settings.pathao_client_id, settings.pathao_client_secret
        return "", ""


@dataclass
class DeliveryResult:
    provider: str
    ok: bool
    simulated: bool
    consignment_id: str = ""
    tracking_code: str = ""
    status: str = ""
    eta: str = ""
    cod_amount: float = 0.0
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        tag = "SIMULATED" if self.simulated else "LIVE"
        if not self.ok:
            return f"[{tag}] {self.provider}: booking FAILED — {self.error}"
        return (
            f"[{tag}] {self.provider}: consignment {self.consignment_id} "
            f"(tracking {self.tracking_code}), status={self.status}, ETA {self.eta}, "
            f"COD {self.cod_amount:.2f}"
        )


class CourierAdapter:
    def book(
        self,
        provider: str,
        recipient: str,
        phone: str,
        address: str,
        product_name: str,
        cod_amount: float = 0.0,
        note: str = "",
    ) -> DeliveryResult:
        provider = (provider or "steadfast").lower().strip()
        if provider not in SUPPORTED_PROVIDERS:
            return DeliveryResult(
                provider,
                False,
                True,
                error=f"unknown provider {provider!r}; expected one of {SUPPORTED_PROVIDERS}",
            )

        # Credentials come from the signed-in shop's own connection, falling
        # back to the machine's .env. Booking a parcel on another shop's
        # courier account would be worse than not booking it at all.
        key, secret = _creds(provider)
        if provider == "steadfast" and key:
            return self._book_steadfast(recipient, phone, address, cod_amount,
                                        note, key, secret)
        if provider == "pathao" and key:
            return self._book_pathao(recipient, phone, address, cod_amount,
                                     note, key, secret)

        return self._simulate(provider, recipient, address, product_name, cod_amount)

    # --- live providers ---

    def _book_steadfast(
        self, recipient: str, phone: str, address: str, cod: float, note: str,
        api_key: str = "", secret_key: str = "",
    ) -> DeliveryResult:
        api_key = api_key or settings.steadfast_api_key
        secret_key = secret_key or settings.steadfast_secret_key
        try:
            resp = requests.post(
                f"{STEADFAST_BASE}/create_order",
                headers={
                    "Api-Key": api_key,
                    "Secret-Key": secret_key,
                    "Content-Type": "application/json",
                },
                json={
                    "invoice": f"INV-{uuid.uuid4().hex[:10].upper()}",
                    "recipient_name": recipient,
                    "recipient_phone": phone,
                    "recipient_address": address,
                    "cod_amount": cod,
                    "note": note,
                },
                timeout=_TIMEOUT,
            )
            data = resp.json()
            consignment = (data.get("consignment") or {}) if isinstance(data, dict) else {}
            if resp.status_code >= 400 or not consignment:
                return DeliveryResult(
                    "steadfast",
                    False,
                    False,
                    error=str(data.get("message", resp.text[:300])),
                    raw=data,
                )
            return DeliveryResult(
                provider="steadfast",
                ok=True,
                simulated=False,
                consignment_id=str(consignment.get("consignment_id", "")),
                tracking_code=str(consignment.get("tracking_code", "")),
                status=str(consignment.get("status", "in_review")),
                cod_amount=float(consignment.get("cod_amount", cod) or cod),
                raw=data,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("steadfast booking failed: %s", exc)
            return DeliveryResult("steadfast", False, False, error=str(exc))

    def _book_pathao(
        self, recipient: str, phone: str, address: str, cod: float, note: str,
        client_id: str = "", client_secret: str = "",
    ) -> DeliveryResult:
        client_id = client_id or settings.pathao_client_id
        client_secret = client_secret or settings.pathao_client_secret
        try:
            token_resp = requests.post(
                f"{PATHAO_BASE}/aladdin/api/v1/issue-token",
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=_TIMEOUT,
            ).json()
            token = token_resp.get("access_token")
            if not token:
                return DeliveryResult(
                    "pathao", False, False, error="could not issue Pathao token",
                    raw=token_resp,
                )
            order = requests.post(
                f"{PATHAO_BASE}/aladdin/api/v1/orders",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "recipient_name": recipient,
                    "recipient_phone": phone,
                    "recipient_address": address,
                    "amount_to_collect": cod,
                    "special_instruction": note,
                },
                timeout=_TIMEOUT,
            ).json()
            data = order.get("data") or {}
            cid = data.get("consignment_id")
            if not cid:
                return DeliveryResult(
                    "pathao", False, False,
                    error=str(order.get("message", "order rejected")), raw=order,
                )
            return DeliveryResult(
                provider="pathao",
                ok=True,
                simulated=False,
                consignment_id=str(cid),
                tracking_code=str(data.get("merchant_order_id", cid)),
                status=str(data.get("order_status", "pending")),
                cod_amount=cod,
                raw=order,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pathao booking failed: %s", exc)
            return DeliveryResult("pathao", False, False, error=str(exc))

    # --- simulation ---

    def _simulate(
        self, provider: str, recipient: str, address: str, product: str, cod: float
    ) -> DeliveryResult:
        cid = f"{provider[:2].upper()}{random.randint(10_000_000, 99_999_999)}"
        eta = (datetime.now(timezone.utc) + timedelta(days=random.randint(1, 3))).strftime(
            "%Y-%m-%d"
        )
        logger.info("SIMULATED %s booking for %s -> %s", provider, product, recipient)
        return DeliveryResult(
            provider=provider,
            ok=True,
            simulated=True,
            consignment_id=cid,
            tracking_code=f"TRK-{uuid.uuid4().hex[:10].upper()}",
            status="pickup_scheduled",
            eta=eta,
            cod_amount=float(cod),
            raw={
                "note": (
                    f"SIMULATED {provider} consignment. No credentials configured, so "
                    "no network call was made. Adding the provider's API keys to .env "
                    "switches this to a live booking with no change to agent logic."
                ),
                "recipient": recipient,
                "address": address,
                "product": product,
            },
        )

    def track(self, provider: str, consignment_id: str) -> dict[str, Any]:
        if provider == "steadfast" and settings.steadfast_api_key:
            try:
                resp = requests.get(
                    f"{STEADFAST_BASE}/status_by_cid/{consignment_id}",
                    headers={
                        "Api-Key": settings.steadfast_api_key,
                        "Secret-Key": settings.steadfast_secret_key,
                    },
                    timeout=_TIMEOUT,
                )
                return {"simulated": False, **resp.json()}
            except Exception as exc:  # noqa: BLE001
                logger.warning("steadfast tracking failed: %s", exc)

        return {
            "simulated": True,
            "consignment_id": consignment_id,
            "delivery_status": random.choice(
                ["pickup_scheduled", "in_transit", "out_for_delivery", "delivered"]
            ),
            "note": "SIMULATED tracking response.",
        }


courier = CourierAdapter()
