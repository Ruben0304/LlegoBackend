# Métodos de Pago en Sucursales

## Resumen de Cambios

Se ha agregado soporte para métodos de pago en las sucursales. Cada sucursal ahora puede especificar qué métodos de pago acepta mediante una lista de IDs de métodos de pago.

## Cambios Implementados

### 1. Modelo de Datos

**Branch Model (`models.py`)**
- Agregado campo `paymentMethodIds: List[str] = []` - Lista de IDs de métodos de pago aceptados

### 2. GraphQL Schema

**Tipos (`schema/branches/types.py`)**
- Agregado campo `paymentMethodIds: List[str]` a `BranchType`, `NearbyBranchType` y `ScoredBranchType`
- Agregado resolver `payment_methods` que retorna la lista completa de objetos `PaymentMethodType`

**Inputs (`schema/branches/inputs.py`)**
- `CreateBranchInput`: Campo `paymentMethodIds` es **obligatorio**
- `UpdateBranchInput`: Campo `paymentMethodIds` es opcional
- `RegisterBranchInput`: Campo `paymentMethodIds` es **obligatorio**

### 3. Mutaciones

**CreateBranch (`schema/branches/mutations.py`)**
- Valida que `paymentMethodIds` no esté vacío
- Verifica que todos los IDs de métodos de pago existan en la base de datos
- Guarda los IDs en la sucursal

**UpdateBranch (`schema/branches/mutations.py`)**
- Permite actualizar `paymentMethodIds`
- Valida que no esté vacío si se proporciona
- Verifica que todos los IDs existan

**RegisterBusiness (`schema/businesses/mutations.py`)**
- Valida `paymentMethodIds` para cada sucursal durante el registro del negocio
- Verifica que todos los IDs existan

### 4. Queries

Todas las queries de sucursales ahora incluyen `paymentMethodIds` en la respuesta:
- `branches`
- `branch`
- `searchBranches`
- `nearbyBranches`

### 5. Migración

Se ha creado un script de migración para agregar el campo a sucursales existentes:

```bash
python scripts/migrate_add_payment_methods_to_branches.py
```

Este script:
- Encuentra todas las sucursales sin el campo `paymentMethodIds`
- Agrega un array vacío `[]` como valor por defecto
- Reporta el número de sucursales actualizadas

## Uso

### Crear Sucursal con Métodos de Pago

```graphql
mutation CreateBranch($input: CreateBranchInput!, $jwt: String) {
  createBranch(input: $input, jwt: $jwt) {
    id
    name
    paymentMethodIds
    paymentMethods {
      id
      currency
      method
    }
  }
}
```

```json
{
  "input": {
    "businessId": "business_id_123",
    "name": "Sucursal Centro",
    "coordinates": { "lat": -12.0464, "lng": -77.0428 },
    "phone": "+51999999999",
    "schedule": { "lun-vie": "9:00-18:00" },
    "tipos": ["RESTAURANTE"],
    "paymentMethodIds": ["payment_method_id_1", "payment_method_id_2"]
  }
}
```

### Consultar Métodos de Pago de una Sucursal

```graphql
query GetBranch($id: String!) {
  branch(id: $id) {
    id
    name
    paymentMethodIds
    paymentMethods {
      id
      currency
      method
    }
  }
}
```

### Actualizar Métodos de Pago

```graphql
mutation UpdateBranch($branchId: String!, $input: UpdateBranchInput!) {
  updateBranch(branchId: $branchId, input: $input) {
    id
    paymentMethodIds
    paymentMethods {
      id
      currency
      method
    }
  }
}
```

```json
{
  "branchId": "branch_id_123",
  "input": {
    "paymentMethodIds": ["payment_method_id_1", "payment_method_id_3"]
  }
}
```

## Validaciones

1. **Creación de Sucursal**: `paymentMethodIds` es obligatorio y no puede estar vacío
2. **Actualización**: Si se proporciona `paymentMethodIds`, no puede estar vacío
3. **Existencia**: Todos los IDs de métodos de pago deben existir en la colección `payment_methods`

## Métodos de Pago Disponibles

Los métodos de pago se gestionan en la colección `payment_methods` de MongoDB. Cada método tiene:
- `id`: Identificador único
- `currency`: Moneda (ej: "CUP", "USD")
- `method`: Tipo de método (ej: "tarjeta", "efectivo", "transferencia")

Para consultar los métodos de pago disponibles, se puede usar el repositorio:

```python
from models import payment_methods_repo

# Obtener todos los métodos de pago
all_methods = await payment_methods_repo.get_all()

# Obtener por moneda
cup_methods = await payment_methods_repo.get_by_currency("CUP")

# Obtener por tipo
card_methods = await payment_methods_repo.get_by_method("tarjeta")
```

## Notas Importantes

- Las sucursales existentes tendrán un array vacío `[]` después de ejecutar la migración
- Los propietarios deberán actualizar sus sucursales para agregar los métodos de pago aceptados
- El campo `paymentMethods` en el tipo GraphQL es un resolver que obtiene los objetos completos de los métodos de pago
- El campo `paymentMethodIds` contiene solo los IDs para optimizar el almacenamiento

## Documentación Actualizada

La documentación en `docs/businesses-branches-api.md` ha sido actualizada para reflejar estos cambios.
