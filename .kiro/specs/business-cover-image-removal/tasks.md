# Plan de Implementación: Eliminación de Cover Image de Business

## Visión General

Este plan implementa la eliminación del campo `coverImage` del modelo Business y la lógica de herencia de avatar para sucursales. Los cambios se realizan de forma incremental, comenzando por los modelos y tipos, luego las mutaciones y repositorios, y finalmente los endpoints.

## Tareas

- [x] 1. Modificar modelo Business y tipos GraphQL
  - [x] 1.1 Eliminar campo coverImage del modelo Business en models.py
    - Remover `coverImage: Optional[str] = None` de la clase Business
    - _Requirements: 1.1_
  - [x] 1.2 Eliminar coverImage y cover_url de BusinessType en schema/businesses/types.py
    - Remover campo `coverImage: Optional[str]`
    - Remover método `cover_url()`
    - _Requirements: 1.4, 1.5_
  - [x] 1.3 Eliminar coverImage de inputs de Business en schema/businesses/inputs.py
    - Remover `coverImage` de CreateBusinessInput
    - Remover `coverImage` de UpdateBusinessInput
    - _Requirements: 1.2, 1.3_

- [x] 2. Actualizar mutaciones y repositorio de Business
  - [x] 2.1 Actualizar register_business en schema/businesses/mutations.py
    - Eliminar asignación de coverImage al crear Business
    - Eliminar coverImage del retorno de BusinessType
    - _Requirements: 1.2_
  - [x] 2.2 Actualizar update_business en schema/businesses/mutations.py
    - Eliminar manejo de input.coverImage
    - Eliminar lógica de borrado de cover anterior
    - Eliminar coverImage del retorno de BusinessType
    - _Requirements: 1.3_
  - [x] 2.3 Actualizar BusinessRepository en repositories/business_repository.py
    - Eliminar coverImage del payload en método create()
    - Eliminar coverImage de _point_to_business() (ignorar si existe en metadata legacy)
    - _Requirements: 1.1, 5.1, 5.2, 5.3_

- [x] 3. Checkpoint - Verificar cambios en Business
  - Asegurar que el código compila sin errores
  - Verificar que no hay referencias a coverImage en Business
  - Preguntar al usuario si hay dudas

- [x] 4. Implementar herencia de avatar en Branch types
  - [x] 4.1 Modificar avatar_url en BranchType
    - Cambiar método a async
    - Agregar parámetro info: Info
    - Implementar lógica: si branch.avatar existe retornarlo, sino buscar business.avatar
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 4.2 Modificar avatar_url en NearbyBranchType
    - Aplicar misma lógica de herencia que BranchType
    - _Requirements: 6.1_
  - [x] 4.3 Modificar avatar_url en ScoredBranchType
    - Aplicar misma lógica de herencia que BranchType
    - _Requirements: 6.2_
  - [ ]* 4.4 Escribir test de propiedad para Avatar Inheritance Logic
    - **Property 1: Avatar Inheritance Logic**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 5. Eliminar endpoint de upload de cover para Business
  - [x] 5.1 Eliminar endpoint /upload/business/cover en api/endpoints/uploads.py
    - Remover función upload_business_cover
    - _Requirements: 2.1, 2.2_

- [ ] 6. Checkpoint - Verificar implementación completa
  - Asegurar que todos los tests pasan
  - Verificar que la herencia de avatar funciona correctamente
  - Preguntar al usuario si hay dudas

- [ ]* 7. Tests adicionales de propiedades
  - [ ]* 7.1 Escribir test de propiedad para Data Integrity
    - **Property 2: Data Integrity on Inheritance**
    - **Validates: Requirements 4.5**
  - [ ]* 7.2 Escribir test de propiedad para Type Consistency
    - **Property 3: Branch Type Consistency**
    - **Validates: Requirements 6.3**

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints aseguran validación incremental
- Los tests de propiedades validan propiedades universales de correctitud
- Los tests unitarios validan ejemplos específicos y casos edge
