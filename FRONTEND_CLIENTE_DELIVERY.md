# Frontend Cliente - Integracion Delivery

## Objetivo
Permitir que cliente cree pedido, reciba decisiones de negocio, reenvie, pague cuando aplique, vea tracking y comparta codigo de entrega.

## Queries principales
- `myOrders(jwt, status, limit, offset)`
- `order(jwt, id)`
- `orderByNumber(jwt, orderNumber)`
- `orderTracking(jwt, orderId)`

## Mutations de pedidos
- `createOrder(jwt, input)`
- `acceptOrderModifications(jwt, orderId)`
- `resubmitOrder(jwt, input)`
- `rejectOrderModifications(jwt, orderId)`
- `cancelOrder(jwt, orderId, reason)`
- `addOrderComment(jwt, input)`
- `rateOrder(jwt, orderId, rating, comment)`

## Mutations de pago (cuando status = pending_payment)
- `initiateQvapayPayment(jwt, orderId)`
- `initiateTrondealerPayment(jwt, orderId)`
- Opcional/manual: `initiatePayment`, `confirmPaymentSent`, `confirmTransferByShortcut`

Nota: para QvaPay/TronDealer ahora el estado pagable esperado es solo `pending_payment`.

## Campos minimos que debe consumir UI
- Identidad: `id`, `orderNumber`, `branchId`
- Estado: `status`, `customerVisibleStatus`, `timeline`, `deadlineAt`
- Pago: `paymentMethod`, `paymentStatus`, `paidAt`
- Totales: `subtotal`, `deliveryFee`, `total`, `currency`
- Tracking: `estimatedDeliveryTime`, `deliveryPerson`, `orderTracking` payload
- Reenvio: `isEditable`, `canCancel`, `resubmissionCount`
- Entrega: `deliveryVerificationCode` (solo visible al cliente owner en `on_the_way`)

## Reglas de UI por estado
- `pending_acceptance`: mostrar espera a tienda + countdown con `deadlineAt`.
- `modified_by_store` / `rejected_by_store`: habilitar editar/reenviar o cancelar.
- `awaiting_delivery_acceptance`: espera de chofer (no pagar todavia).
- `pending_payment`: habilitar botones de pago.
- `accepted`: confirmar pago realizado/validado y espera inicio elaboracion.
- `preparing`: pedido no cancelable.
- `ready_for_pickup` y `on_the_way`: mostrar como "En camino" de cara al cliente.
- `on_the_way`: mostrar codigo al cliente para compartirlo con chofer.
- `delivered`: habilitar calificacion.
- `cancelled`: mostrar motivo en timeline.

## Ejemplo mutation clave (reenvio)
```graphql
mutation Resubmit($jwt: String!, $input: ResubmitOrderInput!) {
  resubmitOrder(jwt: $jwt, input: $input) {
    id
    status
    deadlineAt
    resubmissionCount
    timeline { status message timestamp actor }
  }
}
```
