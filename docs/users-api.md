# API de Usuarios

## Modelo de Usuario

Un usuario puede tener:
- **businessIds**: Lista de IDs de negocios que posee o administra
- **branchIds**: Lista de IDs de sucursales a las que tiene acceso

Los usuarios se almacenan en MongoDB (colección `users`).

---

## Flujo de Imágenes

Para el avatar de usuario:

1. **Subir imagen** via REST endpoint
2. **Recibir** `image_path` en la respuesta
3. **Usar** `image_path` en la mutation GraphQL `updateUser`

---

## Endpoints REST - Upload de Imágenes

### Upload Avatar de Usuario
```
POST /upload/user/avatar
Content-Type: multipart/form-data
Authorization: Bearer {jwt}
```

**Form Data:**
- `image`: Archivo de imagen

**Response:**
```json
{
  "image_path": "users/avatars/6774abc123_1234567890.jpg",
  "image_url": "https://s3.../users/avatars/6774abc123_1234567890.jpg?X-Amz-..."
}
```

> El avatar se convierte a JPG y se redimensiona a 400x400 automáticamente.

---

## Tipos GraphQL

### UserType
```graphql
type UserType {
  id: String!
  name: String!
  email: String!
  phone: String
  role: String!
  avatar: String
  businessIds: [String!]!
  branchIds: [String!]!
  createdAt: DateTime!
  authProvider: String!
  providerUserId: String
  applePrivateEmail: String
  avatarUrl: String       # Presigned URL
}
```

---

## Mutations

### Actualizar Usuario

```graphql
mutation UpdateUser($input: UpdateUserInput!, $jwt: String!) {
  updateUser(input: $input, jwt: $jwt) {
    id
    name
    phone
    avatarUrl
  }
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "name": "Nuevo Nombre",
    "phone": "+51999999999",
    "avatar": "users/avatars/6774abc123_1234567890.jpg"
  }
}
```

---

### Agregar Sucursal a Usuario

Esta mutation permite que un usuario se agregue a sí mismo una sucursal a su lista de acceso.
**Requisito**: El usuario debe tener el negocio (al que pertenece la sucursal) en su lista de `businessIds`.

```graphql
mutation AddBranchToUser($input: AddBranchToUserInput!, $jwt: String!) {
  addBranchToUser(input: $input, jwt: $jwt) {
    id
    name
    branchIds
  }
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "branchId": "6774branch123"
  }
}
```

**Validaciones:**
- Usuario debe estar autenticado
- La sucursal debe existir
- El usuario debe tener el `businessId` (del negocio al que pertenece la sucursal) en su lista de `businessIds`
- La sucursal no debe estar ya en la lista del usuario

---

### Remover Sucursal de Usuario

```graphql
mutation RemoveBranchFromUser($branchId: String!, $jwt: String!) {
  removeBranchFromUser(branchId: $branchId, jwt: $jwt) {
    id
    name
    branchIds
  }
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "branchId": "6774branch123"
}
```

---

### Eliminar Usuario

Elimina la cuenta del usuario autenticado.

```graphql
mutation DeleteUser($jwt: String!) {
  deleteUser(jwt: $jwt)
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG..."
}
```

**Response:**
```json
{
  "data": {
    "deleteUser": true
  }
}
```

---

## Queries

### Obtener Usuario Actual (Me)

```graphql
query Me($jwt: String!) {
  me(jwt: $jwt) {
    id
    name
    email
    phone
    role
    avatarUrl
    businessIds
    branchIds
    createdAt
  }
}
```

### Obtener Usuario por ID

```graphql
query GetUser($id: String!, $jwt: String) {
  user(id: $id, jwt: $jwt) {
    id
    name
    email
    avatarUrl
    businessIds
    branchIds
  }
}
```

### Buscar Usuarios

```graphql
query SearchUsers($query: String!, $jwt: String) {
  searchUsers(query: $query, jwt: $jwt) {
    id
    name
    email
    avatarUrl
  }
}
```

---

## Inputs Reference

### UpdateUserInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | No |
| phone | String | No |
| avatar | String | No |

### AddBranchToUserInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| branchId | String | Sí |

---

## Relación con Negocios y Sucursales

### Al Registrar un Negocio

Cuando un usuario registra un nuevo negocio mediante `registerBusiness`:
1. Se crea el negocio con el `ownerId` del usuario
2. **Automáticamente** se agrega el `businessId` a la lista `businessIds` del usuario

### Agregar Acceso a Sucursales

Para que un usuario pueda agregar una sucursal a su lista:
1. Primero debe tener el `businessId` del negocio padre en su `businessIds`
2. Luego puede usar `addBranchToUser` para agregar la sucursal

### Ejemplo de Flujo

```
1. Usuario A registra "Mi Tienda" (businessId: "abc123")
   → Usuario A ahora tiene businessIds: ["abc123"]

2. Se crean sucursales para "Mi Tienda":
   - Sucursal Centro (branchId: "br001")
   - Sucursal Norte (branchId: "br002")

3. Usuario A quiere acceso a Sucursal Centro:
   → Usa addBranchToUser con branchId: "br001"
   → Usuario A ahora tiene branchIds: ["br001"]
```

---

## Notas de Seguridad

- Solo el usuario autenticado puede modificar su propio perfil
- Solo el usuario puede eliminar su propia cuenta
- Para agregar una sucursal, el usuario debe demostrar propiedad del negocio (tenerlo en businessIds)
- El avatar anterior se elimina de S3 cuando se actualiza
