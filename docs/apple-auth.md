# Autenticacion con Apple

Este documento describe el flujo de inicio de sesion/registro con Apple usando GraphQL.

---

## Configuracion

- `APPLE_CLIENT_ID` debe apuntar al Client ID de Apple (puede ser lista separada por comas).
- `JWT_SECRET` debe estar configurado para emitir tokens internos.

---

## Flujo recomendado

1. El cliente obtiene un **identity token** desde Sign in with Apple.
2. El cliente envia `identityToken` (y `nonce` si aplica) a la mutation `loginWithApple`.
3. El backend valida el token (issuer, audience, expiracion, nonce) y crea/vincula el usuario.
4. El backend responde con `accessToken` y el usuario.

---

## Mutation GraphQL

```graphql
mutation LoginWithApple($input: AppleLoginInput!, $jwt: String) {
  loginWithApple(input: $input, jwt: $jwt) {
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
    "identityToken": "eyJhbGciOi...",
    "nonce": "random-nonce-opcional"
  }
}
```

> `authorizationCode` existe en el input, pero actualmente **no se usa** en el backend.

---

## Validaciones del backend

- Verificacion del token usando las llaves publicas de Apple (`https://appleid.apple.com/auth/keys`).
- `issuer` debe ser `https://appleid.apple.com`.
- `audience` debe coincidir con `APPLE_CLIENT_ID` (soporta multiples valores separados por comas).
- Si `nonce` se envia, debe coincidir con el claim `nonce` del token.

---

## Reglas de creacion/vinculacion de usuario

1. Busca por `providerUserId` + `authProvider = "apple"`.
2. Si no existe y hay `email`, busca por `email` para vincular cuentas.
3. Si no existe, crea usuario nuevo con:
   - `authProvider = "apple"`
   - `providerUserId = sub` del token
   - `applePrivateEmail = is_private_email` del token
   - `password = null`

**Nota:** Si se vincula un usuario existente por email, el campo `authProvider` puede mantenerse en su valor anterior (por ejemplo `"local"`). El backend solo garantiza que `providerUserId` y `applePrivateEmail` queden asociados.

---

## Consideraciones sobre email

Apple puede no incluir `email` en el identity token despues del primer login. El backend actual necesita `email` para vincular o crear el usuario correctamente; si el claim no llega, el login puede fallar. Asegura la primera autorizacion con email disponible.

