# Autenticacion con Google

Este documento describe el flujo de inicio de sesion/registro con Google usando GraphQL.

---

## Configuracion

- `GOOGLE_CLIENT_ID` debe apuntar al Client ID de Google (puede ser lista separada por comas).
- `JWT_SECRET` debe estar configurado para emitir tokens internos.

---

## Flujo recomendado

1. El cliente obtiene un **ID token** (OpenID Connect) desde Google Sign-In.
2. El cliente envia `idToken` (y `nonce` si aplica) a la mutation `loginWithGoogle`.
3. El backend valida el token (audience, expiracion, nonce) y crea/vincula el usuario.
4. El backend responde con `accessToken` y el usuario.

---

## Mutation GraphQL

```graphql
mutation LoginWithGoogle($input: SocialLoginInput!, $jwt: String) {
  loginWithGoogle(input: $input, jwt: $jwt) {
    accessToken
    tokenType
    user {
      id
      name
      email
      phone
      role
      createdAt
    }
  }
}
```

**Variables:**
```json
{
  "input": {
    "idToken": "eyJhbGciOi...",
    "nonce": "random-nonce-opcional"
  }
}
```

> `authorizationCode` existe en el input, pero actualmente **no se usa** en el backend.

---

## Validaciones del backend

- Verificacion del ID token con `google.oauth2.id_token.verify_oauth2_token`.
- `audience` debe coincidir con `GOOGLE_CLIENT_ID` (soporta multiples valores separados por comas).
- Si `nonce` se envia, debe coincidir con el claim `nonce` del token.

---

## Reglas de creacion/vinculacion de usuario

1. Busca por `providerUserId` + `authProvider = "google"`.
2. Si no existe y hay `email`, busca por `email` para vincular cuentas.
3. Si no existe, crea usuario nuevo con:
   - `authProvider = "google"`
   - `providerUserId = sub` del token
   - `password = null`

**Nota:** Si se vincula un usuario existente por email, el campo `authProvider` puede mantenerse en su valor anterior (por ejemplo `"local"`). El backend solo garantiza que `providerUserId` quede asociado.

