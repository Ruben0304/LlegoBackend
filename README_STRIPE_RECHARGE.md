# 🌍 Stripe Payment Link - Recarga Internacional

Sistema de recarga internacional que permite a usuarios de Llego recibir dinero desde el extranjero mediante Stripe Payment Links.

## ✨ Características

- ✅ Link personalizado por usuario
- ✅ Monto ajustable ($5 - $1000 USD)
- ✅ Múltiples métodos de pago internacionales
- ✅ Acreditación automática a la wallet
- ✅ Tracking de uso y estadísticas
- ✅ Sin expiración del link

## 🚀 Configuración Rápida

### 1. Variables de Entorno

Agregar a tu archivo `.env`:

```env
# Stripe Configuration
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
```

### 2. Configurar Webhook en Stripe

1. Ir a: https://dashboard.stripe.com/webhooks
2. Crear nuevo endpoint: `https://tu-backend.com/stripe/webhook`
3. Seleccionar eventos:
   - ✅ `checkout.session.completed`
   - ✅ `payment_intent.succeeded`
   - ✅ `payment_intent.payment_failed`
4. Copiar el "Signing secret" y agregarlo a `.env`

### 3. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 4. Iniciar Servidor

```bash
uvicorn main:app --reload
```

## 📡 Endpoints

### Crear Payment Link

```bash
POST /stripe/create-recharge-link
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "currency": "usd",
  "description": "Recarga internacional para Llego Wallet"
}
```

**Respuesta:**
```json
{
  "payment_link": "https://buy.stripe.com/test_xxxxxxxxxxxxx",
  "link_id": "plink_xxxxxxxxxxxxx",
  "user_id": "user_id",
  "expires_at": null
}
```

### Webhook

```bash
POST /stripe/webhook
stripe-signature: {signature}
```

## 🧪 Testing

### 1. Probar Localmente

```bash
# Ejecutar script de prueba
python scripts/test_recharge_link.py
```

### 2. Escuchar Webhooks (Local)

```bash
# Instalar Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Escuchar webhooks
stripe listen --forward-to localhost:8000/stripe/webhook
```

### 3. Tarjetas de Prueba

- **Número:** `4242 4242 4242 4242`
- **Fecha:** Cualquier fecha futura
- **CVC:** Cualquier 3 dígitos
- **ZIP:** Cualquier código postal

## 📊 Base de Datos

### Colección: `stripe_payment_links`

```javascript
{
  "_id": "plink_xxxxxxxxxxxxx",
  "userId": "user_id",
  "url": "https://buy.stripe.com/...",
  "productId": "prod_xxxxxxxxxxxxx",
  "priceId": "price_xxxxxxxxxxxxx",
  "currency": "usd",
  "isActive": true,
  "totalReceived": 150.00,
  "usageCount": 3,
  "createdAt": ISODate("2024-01-20"),
  "lastUsedAt": ISODate("2024-01-21")
}
```

### Colección: `wallet_transactions`

```javascript
{
  "_id": "pi_xxxxxxxxxxxxx",
  "fromOwnerId": "system",
  "fromOwnerType": "system",
  "toOwnerId": "user_id",
  "toOwnerType": "user",
  "amount": 50.00,
  "currency": "usd",
  "type": "stripe_payment_link",
  "status": "completed",
  "description": "Stripe recharge: $50.0",
  "metadata": {
    "payment_intent_id": "pi_xxxxx",
    "source": "stripe"
  },
  "createdAt": ISODate("2024-01-20"),
  "updatedAt": ISODate("2024-01-20")
}
```

## 🔄 Flujo Completo

```
1. Usuario → Presiona "Recarga Internacional" en la app
2. App → POST /stripe/create-recharge-link (con JWT)
3. Backend → Crea Payment Link de Stripe
4. Backend → Retorna URL del link
5. Usuario → Comparte el link con familiar/amigo
6. Familiar → Abre el link y paga
7. Stripe → Procesa el pago
8. Webhook → Notifica al backend
9. Backend → Acredita dinero a la wallet
10. Usuario → Recibe notificación push (opcional)
```

## 💰 Comisiones de Stripe

- **Tarjetas internacionales:** 2.9% + $0.30 por transacción
- **3D Secure:** Sin costo adicional
- **Conversión de moneda:** 1% adicional si aplica

**Ejemplo:**
- Usuario recibe: $100 USD
- Comisión Stripe: $3.20
- Pagador paga: $103.20 USD

## 📚 Documentación

- [Documentación completa](docs/stripe-recharge-link.md)
- [Integración iOS](docs/stripe-recharge-link-ios.md)
- [Stripe Payment Links](https://stripe.com/docs/payment-links)
- [Stripe Webhooks](https://stripe.com/docs/webhooks)

## 🔒 Seguridad

- ✅ Autenticación JWT requerida
- ✅ Verificación de firma de webhook
- ✅ Metadata con user_id para tracking
- ✅ Límites de monto ($5 - $1000)
- ✅ HTTPS obligatorio en producción

## 🐛 Troubleshooting

### Error: "No autorizado: Token no proporcionado"
- Verificar que el header `Authorization: Bearer {jwt}` esté presente
- Verificar que el JWT sea válido y no haya expirado

### Error: "Usuario no encontrado"
- Verificar que el user_id del JWT exista en la base de datos

### Error: "Error de Stripe: ..."
- Verificar que las variables de entorno de Stripe estén configuradas
- Verificar que la API key sea válida
- Revisar logs del servidor para más detalles

### Webhook no recibe eventos
- Verificar que el webhook esté configurado en Stripe Dashboard
- Verificar que la URL del webhook sea accesible públicamente
- Verificar que el `STRIPE_WEBHOOK_SECRET` sea correcto
- Usar Stripe CLI para probar localmente

## 📈 Próximos Pasos

- [ ] Integrar notificaciones push al recibir pago
- [ ] Agregar analytics de uso de links
- [ ] Implementar desactivación de links
- [ ] Soporte para múltiples monedas (EUR, GBP, etc.)
- [ ] Dashboard de estadísticas de recargas
- [ ] Historial de links creados por usuario

## 🤝 Soporte

Para más información:
- [Documentación de Stripe](https://stripe.com/docs)
- [API Reference](https://stripe.com/docs/api)
- [Webhooks Guide](https://stripe.com/docs/webhooks)

---

**Nota:** Este sistema está diseñado para recargas internacionales. Para pagos locales, usar el sistema de Payment Intents existente.
