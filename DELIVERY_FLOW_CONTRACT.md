# Delivery Flow Contract (Global)

## Scope
Este contrato cubre el flujo completo de pedidos delivery para 3 frontends:
- Cliente
- Negocio
- Chofer

El backend usa la maquina de estados de `OrderStatus` y aplica timeouts automaticos en estados pre-elaboracion.

## Canonical statuses
- `pending_acceptance`
- `modified_by_store`
- `rejected_by_store`
- `awaiting_delivery_acceptance`
- `pending_payment`
- `accepted`
- `preparing`
- `ready_for_pickup`
- `on_the_way`
- `delivered`
- `cancelled`

## Main transitions
- Cliente crea pedido: `pending_acceptance`
- Negocio modifica: `pending_acceptance -> modified_by_store`
- Negocio rechaza: `pending_acceptance -> rejected_by_store`
- Cliente reenvia: `modified_by_store|rejected_by_store|awaiting_delivery_acceptance|pending_payment -> pending_acceptance`
- Negocio acepta delivery: `pending_acceptance -> awaiting_delivery_acceptance`
- Chofer acepta:
  - efectivo: `awaiting_delivery_acceptance -> accepted`
  - transferencia/pasarela: `awaiting_delivery_acceptance -> pending_payment`
- Cliente paga (no efectivo): `pending_payment -> accepted`
- Negocio inicia elaboracion: `accepted -> preparing`
- Negocio listo: `preparing -> ready_for_pickup`
- Chofer recoge: `preparing|ready_for_pickup -> on_the_way`
- Chofer entrega con codigo: `on_the_way -> delivered`

## Timeout SLA (10 min)
Se cancela automaticamente (`cancelled`) si vence `deadlineAt` en:
- `pending_acceptance` (tienda no responde)
- `modified_by_store` (cliente no reenvia)
- `rejected_by_store` (cliente no reenvia)
- `awaiting_delivery_acceptance` (ningun chofer acepta)
- `pending_payment` (cliente no paga)

Worker activo: `services/order_timeout_worker.py`, ciclo cada 60s (registrado en `clients/lifespan.py`).

## Security rule: delivery verification code
`deliveryVerificationCode` ahora solo se expone al cliente dueno del pedido y solo en estado `on_the_way`.
- Negocio y chofer no deben depender de este campo en UI.
- Chofer confirma entrega con codigo que le dicta el cliente.

## Payment type split (cash vs non-cash)
La clasificacion se hace en backend por:
1. Token normalizado del `paymentMethod`.
2. Sets internos (`CASH_PAYMENT_METHODS`, `NON_CASH_PAYMENT_METHODS`).
3. Fallback a metadata de `payment_methods` (`method`, `code`, `name`).
4. Si hay ambiguedad: se trata como no-efectivo (seguro).

## GraphQL naming
Con configuracion por defecto de Strawberry, en GraphQL se exponen en camelCase.
Ejemplo Python `resubmit_order` -> GraphQL `resubmitOrder`.
