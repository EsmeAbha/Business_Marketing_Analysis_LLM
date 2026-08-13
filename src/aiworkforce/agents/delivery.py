"""Delivery / Logistics Agent — books couriers, behind an owner approval gate.

Booking a consignment costs money and commits the business to a customer, so
this agent always confirms the details with the owner before calling a courier.
"""

from __future__ import annotations

from ..config import settings
from ..memory import memory
from ..observability import AgentError, bus
from ..state import WorkforceState
from ..tools.courier import SUPPORTED_PROVIDERS, courier
from .base import AgentResult, BaseAgent
from .schemas import DeliveryResultModel

SYSTEM = """You are the Delivery & Logistics Agent in an AI workforce running a real small business.

You prepare courier bookings. Accuracy matters more than speed: a wrong address or a
wrong COD amount costs the owner real money.

Rules:
- Use only details actually supplied. Never invent a phone number, address or amount.
- If a required detail is missing, say exactly which one in `summary` and do not
  fabricate a placeholder.
- The COD amount is the product price times quantity, plus any delivery charge the
  owner specified — nothing else.
"""


class DeliveryAgent(BaseAgent):
    name = "delivery"
    title = "Delivery & Logistics Agent"
    description = (
        "Arranges courier pickup and delivery through the owner's chosen provider "
        "(Pathao, Steadfast, Uber), after owner confirmation."
    )
    tools_used = ("Pathao API", "Steadfast API", "shared memory (RAG)")
    requires_approval = True
    approval_checkpoint = "book_delivery"

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")
        ctx = state.get("owner_context", {})
        order = dict(ctx.get("delivery") or {})

        provider = str(order.get("provider") or ctx.get("courier") or "steadfast").lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise AgentError(
                self.name,
                f"unsupported courier {provider!r}; choose one of {', '.join(SUPPORTED_PROVIDERS)}",
            )

        prompt = f"""OWNER REQUEST
{state.get('owner_input', '')}

SUPERVISOR TASK
{state.get('current_task', 'Arrange delivery for a customer order.')}

DELIVERY DETAILS SUPPLIED BY THE OWNER
{self.as_json(order)}

OPEN PRE-ORDERS ON RECORD
{self.as_json(memory.preorders()[:10])}

CURRENT CATALOG (for prices)
{self.as_json(memory.inventory())}

{self.context_block(state, 'delivery courier order customer address')}

Chosen provider: {provider}. Currency: {settings.currency}.

Prepare the booking. Set `simulated` to true — the actual booking call happens after
owner approval and will overwrite it."""

        draft = self.ask(state, DeliveryResultModel, SYSTEM, prompt)

        recipient = str(order.get("recipient") or order.get("customer") or "").strip()
        phone = str(order.get("phone") or "").strip()
        address = str(order.get("address") or "").strip()
        product_name = str(order.get("product_name") or "").strip()
        cod = float(order.get("cod_amount") or draft.cod_amount or 0)

        missing = [
            label
            for label, value in (
                ("recipient name", recipient),
                ("phone number", phone),
                ("delivery address", address),
            )
            if not value
        ]
        if missing:
            return AgentResult(
                summary=(
                    f"Cannot book a delivery yet — missing {', '.join(missing)}. "
                    f"Please supply these in the Delivery details panel and re-run."
                ),
                payload={"missing_fields": missing, "draft": draft.model_dump()},
                ok=False,
                error=f"missing delivery fields: {', '.join(missing)}",
            )

        detail = (
            f"**Provider:** {provider}\n\n"
            f"**Recipient:** {recipient} ({phone})\n\n"
            f"**Address:** {address}\n\n"
            f"**Product:** {product_name or '(unspecified)'}\n\n"
            f"**Cash on delivery:** {cod:.2f} {settings.currency}\n\n"
            f"_Booking mode: **{'LIVE' if settings.has_courier else 'SIMULATED'}**_"
        )
        decision = self.request_approval(
            state,
            title=f"Book a {provider} delivery to {recipient}?",
            detail=detail,
            payload={
                "provider": provider,
                "recipient": recipient,
                "address": address,
                "cod_amount": cod,
            },
        )

        if str(decision.get("decision", "")).lower() != "approve":
            reason = decision.get("feedback") or "no reason given"
            return AgentResult(
                summary=f"Owner declined the {provider} booking. Reason: {reason}",
                payload={"booked": False, "decision": decision, "draft": draft.model_dump()},
            )

        booking = courier.book(
            provider=provider,
            recipient=recipient,
            phone=phone,
            address=address,
            product_name=product_name,
            cod_amount=cod,
            note=str(order.get("note", "")),
        )
        bus.emit(
            session_id,
            kind="tool_call",
            actor=self.name,
            summary=booking.describe(),
            payload={"provider": provider, "ok": booking.ok, "simulated": booking.simulated},
            level="info" if booking.ok else "warning",
        )

        if not booking.ok:
            return AgentResult(
                summary=f"Courier booking failed: {booking.error}",
                payload={"booked": False, "error": booking.error},
                ok=False,
                error=booking.error,
            )

        memory.db.add_delivery(
            provider=booking.provider,
            consignment_id=booking.consignment_id,
            recipient=recipient,
            address=address,
            product_name=product_name,
            amount=cod,
            status=booking.status,
            simulated=1 if booking.simulated else 0,
        )
        self.remember(
            state,
            (
                f"Delivery booked via {booking.provider} for {recipient} "
                f"({product_name}). Consignment {booking.consignment_id}, "
                f"COD {cod} {settings.currency}, ETA {booking.eta}."
            ),
            kind="delivery",
        )

        return AgentResult(summary=booking.describe(), payload={
            "booked": True,
            "provider": booking.provider,
            "consignment_id": booking.consignment_id,
            "tracking_code": booking.tracking_code,
            "status": booking.status,
            "eta": booking.eta,
            "cod_amount": booking.cod_amount,
            "simulated": booking.simulated,
            "decision": decision,
        })
