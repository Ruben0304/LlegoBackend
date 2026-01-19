# Wallet - Documentación para Frontend

## Tipos GraphQL

### WalletBalance
```graphql
type WalletBalance {
  local: Float!
  usd: Float!
}
```

### WalletStatusType
```graphql
type WalletStatusType {
  balance: WalletBalance!
  status: String!  # "active", "frozen", "closed"
}
```

### WalletTransactionType
```graphql
type WalletTransactionType {
  id: String!
  fromOwnerId: String
  fromOwnerType: String  # "user" o "branch"
  toOwnerId: String
  toOwnerType: String    # "user" o "branch"
  amount: Float!
  currency: String!      # "local" o "usd"
  type: String!          # "transfer", "deposit", "withdrawal"
  status: String!        # "pending", "completed", "failed", "reversed"
  description: String
  createdAt: DateTime!
  completedAt: DateTime
}
```

## Atributos en Tipos Existentes

### UserType
```graphql
type UserType {
  # ... campos existentes
  wallet: WalletBalance!
  walletStatus: String!
}
```

### BranchType
```graphql
type BranchType {
  # ... campos existentes
  wallet: WalletBalance!
  walletStatus: String!
}
```

## Queries

### myWallet
Obtener balance del usuario actual.
```graphql
query {
  myWallet(jwt: String!): WalletStatusType!
}
```

### myWalletTransactions
Obtener historial de transacciones del usuario actual.
```graphql
query {
  myWalletTransactions(
    jwt: String!
    limit: Int = 50
    skip: Int = 0
    currency: String  # "local" o "usd"
  ): [WalletTransactionType!]!
}
```

### branchWallet
Obtener balance de una sucursal (solo managers o dueño del negocio).
```graphql
query {
  branchWallet(
    branchId: String!
    jwt: String!
  ): WalletStatusType!
}
```

### branchWalletTransactions
Obtener historial de transacciones de una sucursal (solo managers o dueño).
```graphql
query {
  branchWalletTransactions(
    branchId: String!
    jwt: String!
    limit: Int = 50
    skip: Int = 0
    currency: String
  ): [WalletTransactionType!]!
}
```

## Mutations

### transferMoney
Transferir dinero del usuario actual a otro usuario o sucursal.
```graphql
mutation {
  transferMoney(
    jwt: String!
    input: TransferInput!
  ): WalletTransactionType!
}

input TransferInput {
  toOwnerId: String!
  toOwnerType: String!  # "user" o "branch"
  amount: Float!
  currency: String!     # "local" o "usd"
  description: String
}
```

### depositMoney
Depositar dinero en la wallet del usuario actual.
```graphql
mutation {
  depositMoney(
    jwt: String!
    input: DepositInput!
  ): WalletTransactionType!
}

input DepositInput {
  amount: Float!
  currency: String!  # "local" o "usd"
  source: String!    # "bank_transfer", "credit_card", etc.
  description: String
}
```

### withdrawMoney
Retirar dinero de la wallet del usuario actual.
```graphql
mutation {
  withdrawMoney(
    jwt: String!
    input: WithdrawInput!
  ): WalletTransactionType!
}

input WithdrawInput {
  amount: Float!
  currency: String!     # "local" o "usd"
  destination: String!  # Cuenta bancaria, etc.
  description: String
}
```

### branchTransferMoney
Transferir dinero desde wallet de sucursal (solo managers o dueño).
```graphql
mutation {
  branchTransferMoney(
    branchId: String!
    jwt: String!
    input: TransferInput!
  ): WalletTransactionType!
}
```

### branchWithdrawMoney
Retirar dinero de wallet de sucursal (solo managers o dueño).
```graphql
mutation {
  branchWithdrawMoney(
    branchId: String!
    jwt: String!
    input: WithdrawInput!
  ): WalletTransactionType!
}
```

## Validaciones

- `amount` debe ser mayor a 0
- `currency` debe ser "local" o "usd"
- `toOwnerType` debe ser "user" o "branch"
- Solo se permiten transferencias entre wallets de la misma moneda
- Balance debe ser suficiente para transferencias/retiros
- Wallet debe estar en estado "active"

## Estados de Wallet

- `active`: Wallet operativa
- `frozen`: Wallet congelada (no permite operaciones)
- `closed`: Wallet cerrada permanentemente

## Estados de Transacción

- `pending`: Pendiente de aprobación (retiros)
- `completed`: Completada exitosamente
- `failed`: Falló durante procesamiento
- `reversed`: Revertida (reembolso)

## Permisos

### Usuario
- Puede operar su propia wallet
- Puede ver su balance y transacciones
- Puede transferir, depositar y retirar

### Sucursal
- Managers de la sucursal pueden operar la wallet
- Dueño del negocio puede operar wallets de todas sus sucursales
- Pueden transferir y retirar (no depositar directamente)

## Flujo de Pago de Orden

1. Cliente selecciona pagar con wallet
2. Frontend valida balance suficiente
3. Ejecuta `transferMoney` de user a branch
4. Backend actualiza orden a "paid"

## Inicialización

Los campos wallet se crean automáticamente al primer uso. No requiere migración.
