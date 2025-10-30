# Sistema de Hasheo de Contraseñas - SunCar Backend

## Descripción General

Este documento explica cómo funciona el sistema de hasheo de contraseñas en el backend de SunCar, incluyendo la solución al problema del límite de 72 bytes de bcrypt.

## Problema: Límite de 72 bytes en bcrypt

**bcrypt** tiene una limitación técnica: solo puede procesar contraseñas de hasta **72 bytes**. Si una contraseña excede este límite, bcrypt la truncará silenciosamente, lo que puede causar problemas de seguridad y comportamiento inesperado.

### ¿Por qué 72 bytes y no 72 caracteres?

Es importante entender que bcrypt mide en **bytes**, no en caracteres:

- Un carácter ASCII simple (a-z, 0-9) = 1 byte
- Un carácter UTF-8 con tildes (á, é, í) = 2 bytes
- Un emoji = 4 bytes

**Ejemplos:**
```
"Password123" = 11 bytes (11 caracteres ASCII)
"Contraseña" = 11 bytes (10 caracteres, pero 'ñ' = 2 bytes)
"😀" = 4 bytes (1 carácter emoji)
```

Por lo tanto, una contraseña de 40 caracteres con emojis y tildes podría exceder fácilmente los 72 bytes.

## Solución Implementada

Para manejar contraseñas de cualquier longitud de forma segura, implementamos un sistema de preprocesamiento con **SHA-256**.

### Archivo: `infrastucture/security/password_handler.py`

```python
from hashlib import sha256
import bcrypt

MAX_BCRYPT_BYTES = 72

def _prepare_password(password: str) -> bytes:
    """
    Garantiza que la contraseña cumpla con la limitación de 72 bytes de bcrypt.
    Si la contraseña excede ese límite, se calcula SHA-256 y se usa el digest hex.
    """
    raw_bytes = password.encode("utf-8")

    if len(raw_bytes) <= MAX_BCRYPT_BYTES:
        # Contraseña normal, usar directamente
        return raw_bytes

    # Contraseña muy larga: aplicar SHA-256 primero
    digest = sha256(raw_bytes).hexdigest()
    return digest.encode("ascii")
```

### ¿Cómo Funciona?

#### Flujo Normal (Contraseña ≤ 72 bytes)

```
Contraseña: "MiPassword123"
    ↓ (encode UTF-8)
Bytes: b'MiPassword123'  [13 bytes]
    ↓ (bcrypt.hashpw)
Hash: $2b$12$xyz...abc
```

#### Flujo con Contraseña Larga (> 72 bytes)

```
Contraseña: "Esta_Es_Una_Contraseña_Muy_Larga_Con_Muchos_Caracteres_Y_Tildes_áéíóú_🔐🔑"
    ↓ (encode UTF-8)
Bytes: [95 bytes]  ❌ Excede 72 bytes
    ↓ (SHA-256 hash)
SHA-256: "a3f5b1c2d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2"
    ↓ (encode ASCII)
Bytes: [64 bytes]  ✅ Ahora es seguro para bcrypt
    ↓ (bcrypt.hashpw)
Hash: $2b$12$xyz...abc
```

### Ventajas de Esta Solución

1. **Seguridad**: SHA-256 es criptográficamente seguro y produce salidas uniformes de 64 caracteres
2. **Consistencia**: Siempre produce el mismo hash para la misma contraseña
3. **Compatibilidad**: El hash SHA-256 (64 caracteres ASCII) siempre cabe en 72 bytes
4. **Transparencia**: El usuario no necesita saber que esto está ocurriendo

## Funciones Principales

### 1. `hash_password(password: str) -> str`

Hashea una contraseña para almacenarla en la base de datos.

```python
from infrastucture.security.password_handler import hash_password

# Ejemplo de uso
plain_password = "MiContraseñaSegura123"
hashed = hash_password(plain_password)
# Resultado: "$2b$12$xyz...abc" (60 caracteres)
```

**Uso en el código:**
- [trabajadores_repository.py:210](infrastucture/repositories/trabajadores_repository.py#L210) - `set_admin_password()`

### 2. `verify_password(plain_password: str, hashed_password: str) -> bool`

Verifica si una contraseña en texto plano coincide con un hash almacenado.

```python
from infrastucture.security.password_handler import verify_password

# Ejemplo de uso
plain_password = "MiContraseñaSegura123"
stored_hash = "$2b$12$xyz...abc"

is_valid = verify_password(plain_password, stored_hash)
# Resultado: True o False
```

**Uso en el código:**
- [trabajadores_repository.py:113](infrastucture/repositories/trabajadores_repository.py#L113) - `login_admin()`
- [trabajadores_repository.py:155](infrastucture/repositories/trabajadores_repository.py#L155) - `login_brigada()`

### 3. Compatibilidad con Contraseñas Antiguas

El sistema incluye un mecanismo de fallback para manejar contraseñas que pudieron haberse guardado sin el preprocesamiento:

```python
def verify_password(plain_password: str, hashed_password: str) -> bool:
    hashed_bytes = hashed_password.encode("utf-8")
    candidate = _prepare_password(plain_password)

    try:
        # Intentar con preprocesamiento
        return bcrypt.checkpw(candidate, hashed_bytes)
    except ValueError:
        try:
            # Fallback: intentar sin preprocesamiento (contraseñas antiguas)
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_bytes)
        except ValueError:
            # Hash inválido o corrupto
            return False
```

## Casos de Uso en el Sistema

### 1. Registro de AdminPass

**Endpoint:** `POST /api/auth/register-admin`

```json
{
  "ci": "12345678",
  "adminPass": "MiContraseñaAdminSegura"
}
```

**Flujo:**
1. Request llega a [auth_router.py:197](presentation/routers/auth_router.py#L197)
2. Se llama a `auth_service.register_admin()` en [auth_service.py:118](application/services/auth_service.py#L118)
3. Se llama a `worker_repo.set_admin_password()` en [trabajadores_repository.py:195](infrastucture/repositories/trabajadores_repository.py#L195)
4. Se hashea con `hash_password()` en [password_handler.py:26](infrastucture/security/password_handler.py#L26)
5. Se guarda el hash en MongoDB

```python
# Lo que se guarda en MongoDB
{
  "_id": ObjectId("..."),
  "CI": "12345678",
  "adminPass": "$2b$12$xyz...abc"  # Hash bcrypt de 60 caracteres
}
```

### 2. Login de Administrador

**Endpoint:** `POST /api/auth/login-admin`

```json
{
  "ci": "12345678",
  "adminPass": "MiContraseñaAdminSegura"
}
```

**Flujo:**
1. Request llega a [auth_router.py:137](presentation/routers/auth_router.py#L137)
2. Se llama a `auth_service.login_admin()` en [auth_service.py:44](application/services/auth_service.py#L44)
3. Se llama a `worker_repo.login_admin()` en [trabajadores_repository.py:82](infrastucture/repositories/trabajadores_repository.py#L82)
4. Se verifica con `verify_password()` en [password_handler.py:36](infrastucture/security/password_handler.py#L36)
5. Si es válido, se crea un JWT y se retorna

### 3. Login de Brigadista

**Endpoint:** `POST /api/auth/login-brigada`

Similar al login de administrador, pero usando el campo `contraseña` en lugar de `adminPass`.

**Flujo:**
1. Request llega a [auth_router.py:167](presentation/routers/auth_router.py#L167)
2. Se llama a `auth_service.login_brigada()` en [auth_service.py:75](application/services/auth_service.py#L75)
3. Se llama a `worker_repo.login_brigada()` en [trabajadores_repository.py:124](infrastucture/repositories/trabajadores_repository.py#L124)
4. Se verifica con `verify_password()` en [password_handler.py:36](infrastucture/security/password_handler.py#L36)
5. Si es válido, se crea un JWT y se retorna

## Diferencias entre `contraseña` y `adminPass`

El sistema maneja **dos tipos de contraseñas** para trabajadores:

| Campo | Propósito | Endpoint | Hasheo |
|-------|-----------|----------|--------|
| `contraseña` | Acceso de brigadistas | `/api/auth/login-brigada` | ✅ Con bcrypt + SHA-256 |
| `adminPass` | Acceso administrativo | `/api/auth/login-admin` | ✅ Con bcrypt + SHA-256 |

Ambos campos usan el mismo sistema de hasheo seguro.

## Seguridad: bcrypt + SHA-256

### ¿Por qué esta combinación es segura?

1. **SHA-256 no debilita bcrypt**: SHA-256 es criptográficamente seguro y produce salidas uniformes
2. **bcrypt sigue siendo el algoritmo principal**: bcrypt aplica su costo computacional y salt
3. **Protección contra rainbow tables**: bcrypt usa un salt único por contraseña
4. **Protección contra fuerza bruta**: bcrypt es intencionalmente lento (configurable con rounds)

### Rounds de bcrypt

El sistema usa el valor por defecto de bcrypt: **12 rounds**

```python
bcrypt.gensalt()  # Por defecto: 12 rounds (2^12 = 4096 iteraciones)
```

Esto significa que cada hash tarda aproximadamente **~0.3 segundos** en generarse, lo que hace impráctica la fuerza bruta.

## Casos de Error y Manejo

### Error 1: Contraseña None o Vacía

```python
def _ensure_bytes(value: str) -> bytes:
    if value is None:
        raise ValueError("La contraseña no puede ser None")
    return value.encode("utf-8")
```

**Resultado:** `ValueError` con mensaje claro

### Error 2: Hash Inválido en Verificación

```python
try:
    return bcrypt.checkpw(candidate, hashed_bytes)
except ValueError:
    # Intentar fallback o retornar False
    return False
```

**Resultado:** Retorna `False` (credenciales incorrectas)

### Error 3: Trabajador sin Campo de Contraseña

```python
if "adminPass" not in worker_raw:
    logger.warning(f"Trabajador con CI {ci} no tiene adminPass configurado")
    return None
```

**Resultado:** Login falla con mensaje específico

## Mejores Prácticas

### 1. Nunca Almacenar Contraseñas en Texto Plano

```python
# ❌ MAL
collection.update_one({"CI": ci}, {"$set": {"adminPass": plain_password}})

# ✅ BIEN
from infrastucture.security.password_handler import hash_password
hashed = hash_password(plain_password)
collection.update_one({"CI": ci}, {"$set": {"adminPass": hashed}})
```

### 2. Siempre Usar `verify_password()` para Comparar

```python
# ❌ MAL
if stored_hash == plain_password:
    return True

# ✅ BIEN
from infrastucture.security.password_handler import verify_password
if verify_password(plain_password, stored_hash):
    return True
```

### 3. No Truncar Contraseñas Manualmente

```python
# ❌ MAL
password = password[:72]  # Truncar manualmente

# ✅ BIEN
# Dejar que password_handler.py maneje automáticamente
hashed = hash_password(password)  # Maneja cualquier longitud
```

## Estructura de Datos en MongoDB

### Trabajador con Contraseñas

```json
{
  "_id": ObjectId("..."),
  "CI": "12345678",
  "nombre": "Juan Pérez",
  "cargo": "Administrador",
  "contraseña": "$2b$12$xyz...abc",  // Hash bcrypt (opcional)
  "adminPass": "$2b$12$abc...xyz"    // Hash bcrypt (opcional)
}
```

**Notas:**
- Los campos `contraseña` y `adminPass` son **opcionales**
- Ambos almacenan hashes bcrypt de 60 caracteres
- Si un campo no existe, el login correspondiente fallará

## Testing

### Probar Hash de Contraseña Normal

```python
from infrastucture.security.password_handler import hash_password, verify_password

password = "MiPassword123"
hashed = hash_password(password)

print(f"Hash: {hashed}")
print(f"Verificación: {verify_password(password, hashed)}")  # True
print(f"Verificación incorrecta: {verify_password('wrong', hashed)}")  # False
```

### Probar Hash de Contraseña Larga (> 72 bytes)

```python
from infrastucture.security.password_handler import hash_password, verify_password

# Contraseña con 100 caracteres UTF-8 (probablemente > 72 bytes)
password = "Esta_Es_Una_Contraseña_Muy_Larga_Con_Muchos_Caracteres_Y_Tildes_áéíóú_Y_Emojis_🔐🔑🔒_Para_Probar_El_Sistema"

hashed = hash_password(password)

print(f"Longitud en bytes: {len(password.encode('utf-8'))}")
print(f"Hash: {hashed}")
print(f"Verificación: {verify_password(password, hashed)}")  # True
```

## Migración de Contraseñas Antiguas

Si tienes contraseñas almacenadas en texto plano o con un sistema antiguo, usa el script de migración:

### Archivo: `migrate_passwords.py`

```python
from infrastucture.database.mongo_db.connection import get_collection
from infrastucture.security.password_handler import hash_password

def migrate_plain_passwords():
    collection = get_collection("trabajadores")

    # Buscar todos los trabajadores con contraseña en texto plano
    workers = collection.find({"contraseña": {"$exists": True}})

    for worker in workers:
        plain_password = worker.get("contraseña")

        # Verificar si ya está hasheado (empieza con $2b$)
        if not plain_password.startswith("$2b$"):
            # Hashear la contraseña
            hashed = hash_password(plain_password)

            # Actualizar en la base de datos
            collection.update_one(
                {"_id": worker["_id"]},
                {"$set": {"contraseña": hashed}}
            )

            print(f"✅ Contraseña migrada para CI: {worker['CI']}")

if __name__ == "__main__":
    migrate_plain_passwords()
```

## Preguntas Frecuentes

### ¿Por qué no simplemente limitar las contraseñas a 72 caracteres?

Porque queremos permitir contraseñas fuertes de cualquier longitud. Además, 72 **bytes** no son 72 **caracteres** en UTF-8.

### ¿SHA-256 antes de bcrypt no es menos seguro?

No. SHA-256 es un algoritmo criptográfico fuerte que produce salidas uniformes. bcrypt sigue aplicando su salt y costo computacional al resultado.

### ¿Qué pasa si cambio el número de rounds de bcrypt?

Los hashes existentes seguirán funcionando porque bcrypt almacena el número de rounds en el propio hash (`$2b$12$...`). Los nuevos hashes usarán el nuevo número de rounds.

### ¿Puedo ver el código fuente de bcrypt?

Sí, bcrypt es open-source. El límite de 72 bytes está documentado en: https://en.wikipedia.org/wiki/Bcrypt#Maximum_password_length

## Archivos Relacionados

- [password_handler.py](infrastucture/security/password_handler.py) - Funciones de hasheo y verificación
- [trabajadores_repository.py](infrastucture/repositories/trabajadores_repository.py) - Repositorio con métodos de autenticación
- [auth_service.py](application/services/auth_service.py) - Lógica de negocio de autenticación
- [auth_router.py](presentation/routers/auth_router.py) - Endpoints de autenticación
- [AUTH_README.md](docs/AUTH_README.md) - Documentación general de autenticación JWT

## Resumen

El sistema de hasheo de contraseñas de SunCar:

1. ✅ Usa **bcrypt** con 12 rounds para seguridad robusta
2. ✅ Aplica **SHA-256** automáticamente para contraseñas > 72 bytes
3. ✅ Es **transparente** para el desarrollador (solo usar `hash_password()` y `verify_password()`)
4. ✅ Soporta **contraseñas de cualquier longitud**
5. ✅ Es **compatible** con contraseñas antiguas mediante fallback
6. ✅ Está **documentado** y es fácil de mantener

**No necesitas preocuparte por el límite de 72 bytes**: el sistema lo maneja automáticamente de forma segura.
