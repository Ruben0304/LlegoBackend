"""Acciones de cada actor (cliente, negocio, mensajero, admin) sobre un "mundo"
aislado del sandbox. Cada metodo es UNA operacion real contra la API publica
(GraphQL) tal como la hacen las apps.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import E2EClient, GraphQLFailure

ORDER_FIELDS = """
  id orderNumber status paymentStatus paymentMethod deliveryMode currency
  subtotal deliveryFee serviceCharge total
  deadlineAt currentPaymentAttemptId deliveryPersonId
  deliveryVerificationCode canCancel isEditable
  requiresAttention attentionReason rating ratingComment
  items { itemId name quantity finalPrice wasModifiedByStore }
  timeline { status actor message }
"""

ATTEMPT_FIELDS = "id orderId status totalAmount proofUrl"


class World:
    """Negocio + sucursal + productos + usuarios creados para UN test."""

    def __init__(self, client: E2EClient, data: Dict[str, Any]):
        self.client = client
        self.data = data
        self.branch_id: str = data["branchId"]
        self.other_branch_id: str = data["otherBranchId"]
        self.products = data["products"]
        self.payment_methods = data["paymentMethods"]
        self.users = data["users"]
        self.address = data["deliveryAddress"]
        self.service_fee_rate: float = data["serviceFeeRate"]

    @classmethod
    def create(cls, client: E2EClient, **options) -> "World":
        return cls(client, client.rest("POST", "/e2e/world", json=options))

    def token(self, actor: str) -> str:
        return self.users[actor]["token"]

    def user_id(self, actor: str) -> str:
        return self.users[actor]["id"]

    # ------------------------------------------------------------ helpers

    def items(self, **quantities: int) -> List[Dict[str, Any]]:
        return [
            {"itemType": "PRODUCT", "productId": self.products[name]["id"], "quantity": qty}
            for name, qty in quantities.items()
        ]

    def expected_subtotal(self, **quantities: int) -> float:
        return round(
            sum(self.products[name]["price"] * qty for name, qty in quantities.items()), 2
        )

    def _order_mutation(self, name: str, args: str, variables: Dict[str, Any], actor: str):
        query = f"mutation($jwt: String!{args[0]}) {{ {name}({args[1]}jwt: $jwt) {{ {ORDER_FIELDS} }} }}"
        return self.client.gql(query, {"jwt": self.token(actor), **variables})[name]

    def _order_mutation_error(
        self, name: str, args: str, variables: Dict[str, Any], actor: str
    ) -> GraphQLFailure:
        query = f"mutation($jwt: String!{args[0]}) {{ {name}({args[1]}jwt: $jwt) {{ id status }} }}"
        return self.client.gql_error(query, {"jwt": self.token(actor), **variables})

    # ----------------------------------------------------------- customer

    CREATE_ORDER = f"""
    mutation($input: CreateOrderInput!, $jwt: String!) {{
      createOrder(input: $input, jwt: $jwt) {{ {ORDER_FIELDS} }}
    }}"""

    def order_input(
        self,
        items: Optional[List[Dict[str, Any]]] = None,
        payment: str = "cash",
        pickup: bool = False,
        comments: Optional[str] = None,
    ) -> Dict[str, Any]:
        order_input: Dict[str, Any] = {
            "branchId": self.branch_id,
            "items": items if items is not None else self.items(burger=2, soda=1),
            "paymentMethod": self.payment_methods[payment]["id"],
        }
        if pickup:
            order_input["fulfillment"] = {"type": "PICKUP", "pickupBranchId": self.branch_id}
        else:
            order_input["deliveryAddress"] = dict(self.address)
        if comments:
            order_input["comments"] = comments
        return order_input

    def create_order(self, actor: str = "customer", **kwargs) -> Dict[str, Any]:
        return self.client.gql(
            self.CREATE_ORDER, {"input": self.order_input(**kwargs), "jwt": self.token(actor)}
        )["createOrder"]

    def create_order_error(self, order_input: Dict[str, Any], actor: str = "customer") -> GraphQLFailure:
        return self.client.gql_error(
            self.CREATE_ORDER, {"input": order_input, "jwt": self.token(actor)}
        )

    def get_order(self, order_id: str, actor: str = "customer") -> Dict[str, Any]:
        query = f"query($id: String!, $jwt: String!) {{ order(id: $id, jwt: $jwt) {{ {ORDER_FIELDS} }} }}"
        return self.client.gql(query, {"id": order_id, "jwt": self.token(actor)})["order"]

    def get_order_error(self, order_id: str, actor: str) -> GraphQLFailure:
        query = "query($id: String!, $jwt: String!) { order(id: $id, jwt: $jwt) { id } }"
        return self.client.gql_error(query, {"id": order_id, "jwt": self.token(actor)})

    def my_orders(self, actor: str = "customer") -> List[Dict[str, Any]]:
        query = "query($jwt: String!) { myOrders(jwt: $jwt, limit: 50) { orders { id status } } }"
        return self.client.gql(query, {"jwt": self.token(actor)})["myOrders"]["orders"]

    def cancel_order(self, order_id: str, actor: str = "customer", reason: str = "Cambie de idea"):
        return self._order_mutation(
            "cancelOrder", (", $id: String!, $reason: String", "orderId: $id, reason: $reason, "),
            {"id": order_id, "reason": reason}, actor,
        )

    def cancel_order_error(self, order_id: str, actor: str = "customer") -> GraphQLFailure:
        return self._order_mutation_error(
            "cancelOrder", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def accept_modifications(self, order_id: str, actor: str = "customer"):
        return self._order_mutation(
            "acceptOrderModifications", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def reject_modifications(self, order_id: str, actor: str = "customer"):
        return self._order_mutation(
            "rejectOrderModifications", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def resubmit(self, order_id: str, items=None, actor: str = "customer"):
        query = f"""mutation($input: ResubmitOrderInput!, $jwt: String!) {{
          resubmitOrder(input: $input, jwt: $jwt) {{ {ORDER_FIELDS} }} }}"""
        payload: Dict[str, Any] = {"orderId": order_id, "comment": "Reenviado desde E2E"}
        if items is not None:
            payload["items"] = items
        return self.client.gql(query, {"input": payload, "jwt": self.token(actor)})["resubmitOrder"]

    def resubmit_error(self, order_id: str, actor: str = "customer") -> GraphQLFailure:
        query = """mutation($input: ResubmitOrderInput!, $jwt: String!) {
          resubmitOrder(input: $input, jwt: $jwt) { id } }"""
        return self.client.gql_error(
            query, {"input": {"orderId": order_id}, "jwt": self.token(actor)}
        )

    def rate(self, order_id: str, rating: int, comment: str = "Todo perfecto", actor: str = "customer"):
        return self._order_mutation(
            "rateOrder",
            (", $id: String!, $rating: Int!, $comment: String", "orderId: $id, rating: $rating, comment: $comment, "),
            {"id": order_id, "rating": rating, "comment": comment}, actor,
        )

    def rate_error(self, order_id: str, rating: int, actor: str = "customer") -> GraphQLFailure:
        return self._order_mutation_error(
            "rateOrder", (", $id: String!, $rating: Int!", "orderId: $id, rating: $rating, "),
            {"id": order_id, "rating": rating}, actor,
        )

    def comment(self, order_id: str, message: str, actor: str = "customer"):
        query = f"""mutation($input: AddOrderCommentInput!, $jwt: String!) {{
          addOrderComment(input: $input, jwt: $jwt) {{ id }} }}"""
        return self.client.gql(
            query, {"input": {"orderId": order_id, "message": message}, "jwt": self.token(actor)}
        )["addOrderComment"]

    # ------------------------------------------------------------ payment

    def initiate_payment(self, order_id: str, method: str = "transfer", actor: str = "customer"):
        query = f"""mutation($orderId: String!, $pm: String!, $jwt: String!) {{
          initiatePayment(orderId: $orderId, paymentMethodId: $pm, jwt: $jwt) {{
            paymentAttempt {{ {ATTEMPT_FIELDS} }} }} }}"""
        return self.client.gql(
            query,
            {"orderId": order_id, "pm": self.payment_methods[method]["id"], "jwt": self.token(actor)},
        )["initiatePayment"]["paymentAttempt"]

    def initiate_payment_error(self, order_id: str, method: str = "transfer", actor: str = "customer"):
        query = """mutation($orderId: String!, $pm: String!, $jwt: String!) {
          initiatePayment(orderId: $orderId, paymentMethodId: $pm, jwt: $jwt) { paymentAttempt { id } } }"""
        return self.client.gql_error(
            query,
            {"orderId": order_id, "pm": self.payment_methods[method]["id"], "jwt": self.token(actor)},
        )

    CONFIRM_SENT = f"""mutation($id: String!, $proof: String, $jwt: String!) {{
      confirmPaymentSent(paymentAttemptId: $id, proofUrl: $proof, jwt: $jwt) {{ {ATTEMPT_FIELDS} }} }}"""

    def confirm_payment_sent(self, attempt_id: str, proof: Optional[str] = None, actor: str = "customer"):
        return self.client.gql(
            self.CONFIRM_SENT, {"id": attempt_id, "proof": proof, "jwt": self.token(actor)}
        )["confirmPaymentSent"]

    def confirm_payment_sent_error(self, attempt_id: str, actor: str = "customer") -> GraphQLFailure:
        return self.client.gql_error(
            self.CONFIRM_SENT, {"id": attempt_id, "proof": None, "jwt": self.token(actor)}
        )

    def active_attempt(self, order_id: str, actor: str = "owner") -> Optional[Dict[str, Any]]:
        query = f"""query($orderId: String!, $jwt: String!) {{
          activePaymentAttempt(orderId: $orderId, jwt: $jwt) {{ {ATTEMPT_FIELDS} }} }}"""
        return self.client.gql(query, {"orderId": order_id, "jwt": self.token(actor)})[
            "activePaymentAttempt"
        ]

    def payment_attempts(self, order_id: str, actor: str = "customer") -> List[Dict[str, Any]]:
        query = f"""query($orderId: String!, $jwt: String!) {{
          paymentAttemptsByOrder(orderId: $orderId, jwt: $jwt) {{ {ATTEMPT_FIELDS} }} }}"""
        return self.client.gql(query, {"orderId": order_id, "jwt": self.token(actor)})[
            "paymentAttemptsByOrder"
        ]

    CONFIRM_RECEIVED = f"""mutation($id: String!, $jwt: String!) {{
      confirmPaymentReceived(paymentAttemptId: $id, jwt: $jwt) {{ {ATTEMPT_FIELDS} }} }}"""

    def confirm_payment_received(self, attempt_id: str, actor: str = "owner", client=None):
        return (client or self.client).gql(
            self.CONFIRM_RECEIVED, {"id": attempt_id, "jwt": self.token(actor)}
        )["confirmPaymentReceived"]

    def confirm_payment_received_error(self, attempt_id: str, actor: str) -> GraphQLFailure:
        return self.client.gql_error(
            self.CONFIRM_RECEIVED, {"id": attempt_id, "jwt": self.token(actor)}
        )

    def dispute_payment(self, attempt_id: str, reason: str = "No me llego", actor: str = "owner"):
        query = f"""mutation($id: String!, $reason: String!, $jwt: String!) {{
          disputePayment(paymentAttemptId: $id, reason: $reason, jwt: $jwt) {{ {ATTEMPT_FIELDS} }} }}"""
        return self.client.gql(
            query, {"id": attempt_id, "reason": reason, "jwt": self.token(actor)}
        )["disputePayment"]

    # ----------------------------------------------------------- business

    def accept(self, order_id: str, minutes: int = 20, fee: Optional[float] = None, actor: str = "owner"):
        return self._order_mutation(
            "acceptOrder",
            (", $id: String!, $min: Int!, $fee: Float", "orderId: $id, estimatedMinutes: $min, deliveryFee: $fee, "),
            {"id": order_id, "min": minutes, "fee": fee}, actor,
        )

    def accept_error(self, order_id: str, fee: Optional[float] = None, actor: str = "owner") -> GraphQLFailure:
        return self._order_mutation_error(
            "acceptOrder",
            (", $id: String!, $fee: Float", "orderId: $id, estimatedMinutes: 20, deliveryFee: $fee, "),
            {"id": order_id, "fee": fee}, actor,
        )

    def reject(self, order_id: str, reason: str = "Cerramos temprano", actor: str = "owner"):
        return self._order_mutation(
            "rejectOrder", (", $id: String!, $reason: String!", "orderId: $id, reason: $reason, "),
            {"id": order_id, "reason": reason}, actor,
        )

    def reject_error(self, order_id: str, actor: str = "owner") -> GraphQLFailure:
        return self._order_mutation_error(
            "rejectOrder", (", $id: String!", 'orderId: $id, reason: "x", '), {"id": order_id}, actor
        )

    MODIFY = f"""mutation($input: ModifyOrderItemsInput!, $jwt: String!) {{
      modifyOrderItems(input: $input, jwt: $jwt) {{ {ORDER_FIELDS} }} }}"""

    def modify(self, order_id: str, items, reason: str = "Se acabo el refresco", actor: str = "owner"):
        return self.client.gql(
            self.MODIFY,
            {"input": {"orderId": order_id, "items": items, "reason": reason}, "jwt": self.token(actor)},
        )["modifyOrderItems"]

    def modify_error(self, order_id: str, items, actor: str = "owner") -> GraphQLFailure:
        return self.client.gql_error(
            self.MODIFY,
            {"input": {"orderId": order_id, "items": items, "reason": "x"}, "jwt": self.token(actor)},
        )

    UPDATE_STATUS = f"""mutation($input: UpdateOrderStatusInput!, $jwt: String!) {{
      updateOrderStatus(input: $input, jwt: $jwt) {{ {ORDER_FIELDS} }} }}"""

    def set_status(self, order_id: str, status: str, actor: str = "owner"):
        return self.client.gql(
            self.UPDATE_STATUS,
            {"input": {"orderId": order_id, "status": status}, "jwt": self.token(actor)},
        )["updateOrderStatus"]

    def set_status_error(self, order_id: str, status: str, actor: str) -> GraphQLFailure:
        return self.client.gql_error(
            self.UPDATE_STATUS,
            {"input": {"orderId": order_id, "status": status}, "jwt": self.token(actor)},
        )

    def start_preparing(self, order_id: str, actor: str = "owner"):
        return self.set_status(order_id, "PREPARING", actor)

    def mark_ready(self, order_id: str, actor: str = "owner"):
        return self._order_mutation(
            "markOrderReady", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def mark_ready_error(self, order_id: str, actor: str) -> GraphQLFailure:
        return self._order_mutation_error(
            "markOrderReady", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def branch_orders(self, actor: str = "owner", branch_id: Optional[str] = None):
        query = """query($b: String!, $jwt: String!) {
          branchOrders(branchId: $b, jwt: $jwt) { orders { id status } totalCount } }"""
        return self.client.gql(query, {"b": branch_id or self.branch_id, "jwt": self.token(actor)})[
            "branchOrders"
        ]

    def branch_orders_error(self, actor: str, branch_id: Optional[str] = None) -> GraphQLFailure:
        query = """query($b: String!, $jwt: String!) {
          branchOrders(branchId: $b, jwt: $jwt) { totalCount } }"""
        return self.client.gql_error(query, {"b": branch_id or self.branch_id, "jwt": self.token(actor)})

    # ------------------------------------------------------------- courier

    def courier_accept(self, order_id: str, actor: str = "courier", client=None):
        query = f"""mutation($id: String!, $jwt: String!) {{
          acceptOrderForPayment(orderId: $id, jwt: $jwt) {{ {ORDER_FIELDS} }} }}"""
        return (client or self.client).gql(query, {"id": order_id, "jwt": self.token(actor)})[
            "acceptOrderForPayment"
        ]

    def courier_release(self, order_id: str, actor: str = "courier"):
        return self._order_mutation(
            "rejectOrderForPayment", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def courier_release_error(self, order_id: str, actor: str = "courier") -> GraphQLFailure:
        return self._order_mutation_error(
            "rejectOrderForPayment", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def courier_pickup(self, order_id: str, actor: str = "courier"):
        return self._order_mutation(
            "confirmPickup", (", $id: String!", "orderId: $id, "), {"id": order_id}, actor
        )

    def courier_deliver(self, order_id: str, code: str, actor: str = "courier"):
        return self._order_mutation(
            "confirmDelivery", (", $id: String!, $code: String!", "orderId: $id, deliveryCode: $code, "),
            {"id": order_id, "code": code}, actor,
        )

    def courier_deliver_error(self, order_id: str, code: str, actor: str = "courier") -> GraphQLFailure:
        return self._order_mutation_error(
            "confirmDelivery", (", $id: String!, $code: String!", "orderId: $id, deliveryCode: $code, "),
            {"id": order_id, "code": code}, actor,
        )

    # --------------------------------------------------------------- admin

    def force_status(self, order_id: str, status: str, actor: str = "admin"):
        query = f"""mutation($id: String!, $s: OrderStatusEnum!, $jwt: String!) {{
          forceOrderStatus(orderId: $id, status: $s, reason: "E2E", jwt: $jwt) {{ {ORDER_FIELDS} }} }}"""
        return self.client.gql(query, {"id": order_id, "s": status, "jwt": self.token(actor)})[
            "forceOrderStatus"
        ]

    def force_status_error(self, order_id: str, status: str, actor: str) -> GraphQLFailure:
        query = """mutation($id: String!, $s: OrderStatusEnum!, $jwt: String!) {
          forceOrderStatus(orderId: $id, status: $s, reason: "E2E", jwt: $jwt) { id } }"""
        return self.client.gql_error(query, {"id": order_id, "s": status, "jwt": self.token(actor)})

    def orders_requiring_attention(self, actor: str = "admin") -> List[Dict[str, Any]]:
        query = """query($jwt: String!) { ordersRequiringAttention(jwt: $jwt, limit: 200) {
          orders { id status requiresAttention attentionReason } } }"""
        return self.client.gql(query, {"jwt": self.token(actor)})["ordersRequiringAttention"]["orders"]

    # ---------------------------------------------------------- sandbox

    def expire(self, order_id: str) -> Dict[str, Any]:
        """Simula que vencio el plazo del pedido (misma logica que el worker)."""
        return self.client.rest("POST", f"/e2e/orders/{order_id}/expire")

    def patch_branch(self, **fields) -> Dict[str, Any]:
        return self.client.rest("PATCH", f"/e2e/branches/{self.branch_id}", json=fields)

    # ------------------------------------------------ flujos compuestos

    def delivery_order_ready_to_pay(self, **kwargs) -> Dict[str, Any]:
        """Cliente pide por transferencia -> negocio acepta -> mensajero acepta."""
        order = self.create_order(payment="transfer", **kwargs)
        self.accept(order["id"])
        return self.courier_accept(order["id"])

    def paid_transfer_order(self) -> Dict[str, Any]:
        """... -> cliente transfiere -> negocio confirma. Queda ACCEPTED y pagado."""
        order = self.delivery_order_ready_to_pay()
        attempt = self.initiate_payment(order["id"])
        self.confirm_payment_sent(attempt["id"])
        self.confirm_payment_received(attempt["id"])
        return self.get_order(order["id"])

    def deliver(self, order_id: str) -> Dict[str, Any]:
        """Negocio prepara -> listo -> mensajero recoge -> entrega con codigo."""
        self.start_preparing(order_id)
        self.mark_ready(order_id)
        on_the_way = self.courier_pickup(order_id)
        assert on_the_way["status"] == "ON_THE_WAY", on_the_way
        code = self.get_order(order_id)["deliveryVerificationCode"]
        assert code and len(code) == 6, "El cliente debe ver un codigo de 6 digitos en camino"
        return self.courier_deliver(order_id, code)
