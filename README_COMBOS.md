# Sistema de Combos - Llego Backend

## Descripción

Sistema completo de combos personalizables que permite a los negocios crear ofertas combinadas de productos con descuentos y opciones configurables.

## Características

- ✅ Combos con múltiples slots de selección
- ✅ Opciones por defecto y alternativas
- ✅ Ajustes de precio por opción
- ✅ Modifiers disponibles por producto
- ✅ Descuentos (porcentaje o monto fijo)
- ✅ Cálculo de precios mínimos para catálogo
- ✅ Productos representativos para UI
- ✅ Filtrado por sucursal y categoría

## Estructura de un Combo

```
Combo
├── Información básica (nombre, descripción, imagen)
├── Descuento (tipo y valor)
├── Slots (grupos de selección)
│   ├── Slot 1: "Elige tu proteína"
│   │   ├── minSelections: 1
│   │   ├── maxSelections: 1
│   │   └── Opciones
│   │       ├── Opción 1: Pollo (+$0)
│   │       ├── Opción 2: Carne (+$2)
│   │       └── Opción 3: Pescado (+$3)
│   └── Slot 2: "Elige tus acompañantes"
│       ├── minSelections: 2
│       ├── maxSelections: 3
│       └── Opciones
│           ├── Opción 1: Papas (+$0)
│           ├── Opción 2: Ensalada (+$1)
│           └── Opción 3: Arroz (+$0.5)
└── Pricing calculado dinámicamente
```

## Campos de Pricing

### Campos Existentes

- **basePrice**: Precio base con selecciones por defecto
- **finalPrice**: Precio final con descuento aplicado (selecciones por defecto)
- **savings**: Ahorro con selecciones por defecto

### Nuevos Campos (para Catálogo)

- **startingBasePrice**: Precio mínimo base válido (antes del descuento)
- **startingFinalPrice**: Precio mínimo final válido (después del descuento)
  - ⭐ **USAR ESTE CAMPO para mostrar "Desde $X" en catálogo**
- **startingSavings**: Ahorro mínimo válido

### ¿Por qué dos sets de campos?

Los campos `basePrice`, `finalPrice` y `savings` calculan el precio usando las **opciones por defecto** del combo, que pueden no ser las más baratas.

Los campos `starting*` calculan el precio usando la **combinación válida más barata**, que es lo que debe mostrarse en catálogo como "Desde $X".

**Ejemplo:**
```
Combo: Hamburguesa + Bebida
- Slot 1 (Hamburguesa): 
  - Simple: $5 (por defecto)
  - Doble: $8
- Slot 2 (Bebida):
  - Agua: $1
  - Refresco: $2 (por defecto)
- Descuento: 10%

basePrice = $5 + $2 = $7
finalPrice = $7 * 0.9 = $6.30

startingBasePrice = $5 + $1 = $6 (combinación más barata)
startingFinalPrice = $6 * 0.9 = $5.40 ← Mostrar "Desde $5.40"
```

## GraphQL API

### Queries

```graphql
# Obtener un combo específico
query {
  combo(comboId: "123") {
    id
    name
    startingFinalPrice  # Para catálogo
    startingSavings
  }
}

# Obtener combos de una sucursal
query {
  combosByBranch(branchId: "branch123", availableOnly: true) {
    id
    name
    startingFinalPrice
  }
}

# Obtener todos los combos con filtros
query {
  allCombos(
    availableOnly: true
    branchTipo: "restaurante"
    productCategoryId: "cat123"
  ) {
    id
    name
    startingFinalPrice
  }
}
```

### Mutations

```graphql
# Crear combo
mutation {
  createCombo(input: {
    branchId: "branch123"
    name: "Combo Familiar"
    description: "Para toda la familia"
    slots: [...]
    discountType: PERCENTAGE
    discountValue: 15
  }) {
    id
    name
  }
}

# Actualizar combo
mutation {
  updateCombo(input: {
    comboId: "combo123"
    name: "Nuevo nombre"
    availability: true
  }) {
    id
    name
  }
}

# Activar/desactivar combo
mutation {
  toggleComboAvailability(
    comboId: "combo123"
    availability: false
  ) {
    id
    availability
  }
}
```

## Archivos Principales

### Schema GraphQL
- `schema/combos/types.py` - Definiciones de tipos y resolvers
- `schema/combos/queries.py` - Queries de combos
- `schema/combos/mutations.py` - Mutations de combos
- `schema/combos/inputs.py` - Input types

### Dominio
- `domain/models.py` - Modelo de dominio `Combo`

### Repositorio
- `repositories/combos_repository.py` - Acceso a datos

### Tests
- `tests/test_combo_pricing.py` - Tests de cálculo de precios

## Documentación Adicional

- [Especificación de Campos de Pricing](docs/COMBO_PRICING_FIELDS.md)
- [Ejemplos de Queries GraphQL](docs/COMBO_PRICING_EXAMPLE.graphql)
- [Resumen de Implementación](docs/COMBO_PRICING_IMPLEMENTATION_SUMMARY.md)

## Scripts de Prueba

```bash
# Probar campos de pricing en combos reales
python3 scripts/test_combo_pricing_fields.py

# Probar un combo específico
python3 scripts/test_combo_pricing_fields.py <combo_id>
```

## Tests

```bash
# Ejecutar tests de pricing
python3 -m pytest tests/test_combo_pricing.py -v

# Ejecutar todos los tests de combos
python3 -m pytest tests/ -k combo -v
```

## Uso en Frontend

### Catálogo de Combos

```typescript
// Query para catálogo
const GET_COMBOS = gql`
  query GetCombosCatalog($branchId: String!) {
    combosByBranch(branchId: $branchId, availableOnly: true) {
      id
      name
      description
      imageUrl
      startingFinalPrice
      startingSavings
      currency
      representativeProducts {
        id
        name
        imageUrl
      }
    }
  }
`;

// Componente
function ComboCard({ combo }) {
  return (
    <div className="combo-card">
      <img src={combo.imageUrl} alt={combo.name} />
      <h3>{combo.name}</h3>
      <p>{combo.description}</p>
      
      {/* Precio mínimo */}
      <p className="price">
        Desde {combo.currency} ${combo.startingFinalPrice.toFixed(2)}
      </p>
      
      {/* Ahorro */}
      {combo.startingSavings > 0 && (
        <p className="savings">
          Ahorras ${combo.startingSavings.toFixed(2)}
        </p>
      )}
      
      {/* Productos representativos */}
      <div className="products">
        {combo.representativeProducts.map(product => (
          <img key={product.id} src={product.imageUrl} />
        ))}
      </div>
    </div>
  );
}
```

### Detalle de Combo

```typescript
// Query para detalle
const GET_COMBO_DETAIL = gql`
  query GetComboDetail($comboId: String!) {
    combo(comboId: $comboId) {
      id
      name
      description
      imageUrl
      
      # Pricing
      startingFinalPrice
      startingSavings
      basePrice
      finalPrice
      
      # Descuento
      discountType
      discountValue
      
      # Slots para personalización
      slots {
        id
        name
        description
        minSelections
        maxSelections
        isRequired
        
        options {
          productId
          isDefault
          priceAdjustment
          
          product {
            id
            name
            price
            imageUrl
          }
          
          availableModifiers {
            name
            priceAdjustment
          }
        }
      }
    }
  }
`;
```

## Reglas de Negocio

1. **Slots Obligatorios**: Si `minSelections > 0`, el slot debe incluirse en el precio mínimo
2. **Slots Opcionales**: Si `minSelections = 0`, el slot NO se incluye en el precio "desde"
3. **Selecciones Múltiples**: Si `minSelections > 1`, se seleccionan las N opciones más baratas
4. **Ajustes de Precio**: Se suman al precio base del producto
5. **Descuentos**: Se aplican sobre la suma total de productos seleccionados
6. **Modifiers**: Solo se incluyen modifiers obligatorios en el precio "desde"

## Notas de Implementación

- Los campos de pricing se calculan dinámicamente en cada query
- No hay caché de precios (considerar si hay problemas de performance)
- Los precios se redondean a 2 decimales
- Los descuentos negativos se tratan como 0
- Los precios negativos se tratan como 0

## Changelog

### 2024-03-24
- ✅ Agregados campos `startingBasePrice`, `startingFinalPrice`, `startingSavings`
- ✅ Implementada lógica de cálculo de precio mínimo válido
- ✅ Creados tests unitarios (7 tests)
- ✅ Documentación completa
- ✅ Script de prueba para combos reales
