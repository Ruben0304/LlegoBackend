# API de Usuarios

Documentación para integración frontend multiplataforma.

---

## Modelo de Usuario

```typescript
interface User {
  id: string;
  name: string;
  email: string;
  phone?: string;
  password?: string;         // Solo para auth local (no expuesto en API)
  role: string;              // "customer" | "merchant" | "admin"
  avatar?: string;           // Path en S3
  businessIds: string[];     // Negocios que posee
  branchIds: string[];       // Sucursales con acceso
  createdAt: DateTime;
  authProvider: string;      // "local" | "google" | "apple"
  providerUserId?: string;   // ID del proveedor social
  applePrivateEmail?: string;// Email privado de Apple
  location?: {               // Ubicación actual (GeoJSON)
    type: "Point";
    coordinates: [lng, lat];
  };
  
  // Campo computado (resolver)
  avatarUrl?: string;        // Presigned URL
}
```

---

## Autenticación

### Registro
```graphql
mutation Register($input: RegisterInput!) {
  register(input: $input) {
    access_token
    token_type
    user {
      id
      name
      email
      role
    }
  }
}
```
```json
{
  "input": {
    "name": "Juan Pérez",
    "email": "juan@ejemplo.com",
    "password": "secreto123",
    "phone": "+51999999999"
  }
}
```
> El rol siempre es `customer`. Solo modificable vía DB.

### Login Email/Password
```graphql
mutation Login($input: LoginInput!) {
  login(input: $input) {
    access_token
    user { id name email role }
  }
}
```

### Login con Google
```graphql
mutation LoginGoogle($input: SocialLoginInput!) {
  loginWithGoogle(input: $input) {
    access_token
    user { id name email role }
  }
}
```
```json
{
  "input": {
    "id_token": "eyJhbG...",
    "nonce": "random_nonce_string"
  }
}
```

### Login con Apple
```graphql
mutation LoginApple($input: AppleLoginInput!) {
  loginWithApple(input: $input) {
    access_token
    user { id name email role }
  }
}
```
```json
{
  "input": {
    "identity_token": "eyJhbG...",
    "nonce": "random_nonce_string"
  }
}
```

---

## Queries

### Usuario Actual
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

### Usuario por ID (Admin/Manager)
```graphql
query GetUser($id: String!, $jwt: String!) {
  user(id: $id, jwt: $jwt) {
    id
    name
    email
    avatarUrl
  }
}
```
> Requiere rol `admin` o `manager`.

### Buscar Usuarios (Admin/Manager)
```graphql
query SearchUsers($query: String!, $jwt: String!) {
  searchUsers(query: $query, jwt: $jwt) {
    id
    name
    email
    avatarUrl
  }
}
```

---

## Mutations

### Actualizar Perfil

**Paso 1: Subir Avatar (opcional)**
```bash
curl -X POST "/upload/user/avatar" \
  -H "Authorization: Bearer {jwt}" \
  -F "image=@foto.jpg"
```
Response:
```json
{
  "image_path": "users/avatars/6774abc123_1234567890.jpg",
  "image_url": "https://s3.../users/avatars/..."
}
```

**Paso 2: Actualizar datos**
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
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "name": "Juan Carlos Pérez",
    "phone": "+51988888888",
    "avatar": "users/avatars/6774abc123_1234567890.jpg"
  }
}
```

### Actualizar Ubicación
```graphql
mutation UpdateLocation($input: UpdateLocationInput!, $jwt: String) {
  updateLocation(input: $input, jwt: $jwt) {
    id
    name
  }
}
```
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "longitude": -77.0428,
    "latitude": -12.0464
  }
}
```
> Importante para scoring por cercanía en productos y sucursales.

### Agregar Sucursal
```graphql
mutation AddBranchToUser($input: AddBranchToUserInput!, $jwt: String!) {
  addBranchToUser(input: $input, jwt: $jwt) {
    id
    branchIds
  }
}
```
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "branchId": "6774branch123"
  }
}
```

**Validaciones:**
- Usuario autenticado
- Sucursal existe
- El `businessId` de la sucursal está en `businessIds` del usuario
- La sucursal no está ya en `branchIds`

### Remover Sucursal
```graphql
mutation RemoveBranchFromUser($branchId: String!, $jwt: String!) {
  removeBranchFromUser(branchId: $branchId, jwt: $jwt) {
    id
    branchIds
  }
}
```

### Eliminar Cuenta
```graphql
mutation DeleteUser($jwt: String!) {
  deleteUser(jwt: $jwt)
}
```
Response: `true` si exitoso.

---

## Inputs Reference

### RegisterInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | Sí |
| email | String | Sí |
| password | String | Sí |
| phone | String | No |

### LoginInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| email | String | Sí |
| password | String | Sí |

### SocialLoginInput (Google)
| Campo | Tipo | Requerido |
|-------|------|-----------|
| id_token | String | Sí |
| authorization_code | String | No |
| nonce | String | No |

### AppleLoginInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| identity_token | String | Sí |
| authorization_code | String | No |
| nonce | String | No |

### UpdateUserInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | No |
| phone | String | No |
| avatar | String | No |

### UpdateLocationInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| longitude | Float | Sí |
| latitude | Float | Sí |

### AddBranchToUserInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| branchId | String | Sí |

---

## Notas de Seguridad

- Solo el usuario autenticado puede modificar su propio perfil
- Solo el usuario puede eliminar su propia cuenta
- Para agregar una sucursal, debe tener el negocio en `businessIds`
- El avatar anterior se elimina de S3 al actualizar
- Queries de usuarios (`users`, `user`, `searchUsers`) requieren rol `admin` o `manager`
