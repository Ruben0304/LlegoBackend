# Frontend Negocio - Integracion Delivery

## Objetivo
Gestionar decision de negocio, tiempo estimado, modificaciones/rechazos, y avance a elaboracion/listo.

## Queries principales
- `pendingBranchOrders(jwt, branchId)`
- `branchOrders(jwt, branchId, status, fromDate, toDate, limit, offset)`
- `order(jwt, id)`
- `orderStats(jwt, branchId, period)`

## Mutations principales
- `acceptOrder(jwt, orderId, estimatedMinutes, deliveryFee?)`
- `modifyOrderItems(jwt, input)`
- `rejectOrder(jwt, orderId, reason)`
- `updateOrderStatus(jwt, input)` (ej. pasar a `preparing`)
- `markOrderReady(jwt, orderId)`
- `addOrderComment(jwt, input)`

## Campos minimos que debe consumir UI
- Identidad: `id`, `orderNumber`, `customerId`
- Estado: `status`, `timeline`, `deadlineAt`
- Pago: `paymentMethod`, `paymentStatus`, `paidAt`
- Totales: `subtotal`, `deliveryFee`, `total`, `currency`
- Operativa: `deliveryMode`, `deliveryPersonId`, `estimatedDeliveryTime`
- Cliente: `customer { id name phone }`
- Direcciones: `deliveryAddress`, `pickupAddress`

## Reglas operativas de negocio
- En `pending_acceptance` debe decidir antes de `deadlineAt`.
- Si acepta delivery: pedido pasa a `awaiting_delivery_acceptance`.
- Si modifica/rechaza: cliente puede reenviar; pedido vuelve a `pending_acceptance`.
- No pasar a `preparing` si es no-efectivo y `paymentStatus != completed`.
- Si es efectivo y chofer ya acepto: puede pasar a `preparing` sin pago previo.
- Desde `preparing`, pedido se considera no cancelable.

## Recomendacion de tablero
Separar columnas por estado pre-elaboracion:
- Pendientes tienda: `pending_acceptance`
- Espera cliente: `modified_by_store`, `rejected_by_store`
- Espera chofer: `awaiting_delivery_acceptance`
- Espera pago: `pending_payment`
- Operativos: `accepted`, `preparing`, `ready_for_pickup`, `on_the_way`
