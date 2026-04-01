# Frontend Chofer - Integracion Delivery

## Objetivo
Tomar pedidos disponibles, habilitar pago cuando aplica, recoger, trackear y completar entrega por codigo.

## Queries principales
- `availableOrdersForDelivery(jwt, latitude, longitude, radiusKm)`
- `myCurrentDelivery(jwt)`
- `myDeliveries(jwt, status, page, pageSize)`
- `myDeliveryStats(jwt)`
- `orderTracking(jwt, orderId)`

## Mutations principales
- `acceptOrderForPayment(jwt, orderId)`
- `rejectOrderForPayment(jwt, orderId)`
- `acceptDelivery(jwt, orderId)` (compat legacy)
- `confirmPickup(jwt, orderId)`
- `updateDeliveryLocation(jwt, input)`
- `confirmDelivery(jwt, orderId, deliveryCode)`

## Reglas operativas chofer
- Solo ve disponibles en `awaiting_delivery_acceptance`.
- Si acepta:
  - efectivo -> pedido pasa a `accepted`
  - no efectivo -> pasa a `pending_payment`
- Puede rechazar en `pending_payment` para liberar pedido.
- Recogida permitida desde `preparing` o `ready_for_pickup`.
- Entrega solo desde `on_the_way` y con codigo valido.

## Campos minimos que debe consumir UI
- Identidad: `id`, `orderNumber`
- Estado: `status`, `timeline`
- Rutas: `deliveryAddress.coordinates`, `pickupAddress.coordinates`
- Contactos: `customer { name phone }`, `branch { address }`
- ETA: `estimatedDeliveryTime`, `estimatedMinutesRemaining`

## Seguridad de codigo de entrega
- `deliveryVerificationCode` no debe mostrarse en app chofer.
- El chofer debe pedir al cliente el codigo mostrado en app cliente.

## Ejemplo mutation entrega
```graphql
mutation ConfirmDelivery($jwt: String!, $orderId: String!, $code: String!) {
  confirmDelivery(jwt: $jwt, orderId: $orderId, deliveryCode: $code) {
    id
    status
    completedAt
  }
}
```
