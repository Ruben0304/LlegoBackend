"""Recargas de billetera por Stripe (context.md §12, bug 2).

Antes `WalletRepository.add_balance` fallaba siempre (AttributeError) y, de haber
funcionado, sumaba en `wallet.balance`, un campo que nadie lee: Stripe cobraba y el
usuario no veía el saldo. Ahora acredita en `wallet.usd` y una sola vez por cobro.
"""
import asyncio
from unittest.mock import patch

from bson import ObjectId

from repositories import wallet_repository
from repositories.wallet_repository import WalletRepository


class _Resultado:
    def __init__(self, upserted_id=None):
        self.upserted_id = upserted_id


class _Coleccion:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    @staticmethod
    def _coincide(doc, filtro):
        return all(doc.get(k) == v for k, v in filtro.items())

    async def find_one(self, filtro, proyeccion=None):
        return next((d for d in self.docs if self._coincide(d, filtro)), None)

    async def insert_one(self, doc):
        self.docs.append({"_id": ObjectId(), **doc})

    async def update_one(self, filtro, cambios, upsert=False):
        doc = await self.find_one(filtro)
        if doc is None:
            if not upsert:
                return _Resultado()
            nuevo = {"_id": ObjectId(), **filtro, **cambios.get("$setOnInsert", {})}
            self.docs.append(nuevo)
            return _Resultado(nuevo["_id"])
        for campo, valor in cambios.get("$inc", {}).items():
            raiz, hoja = campo.split(".")
            doc.setdefault(raiz, {})[hoja] = doc.get(raiz, {}).get(hoja, 0) + valor
        return _Resultado()


class _Base(dict):
    def __getitem__(self, nombre):
        return self.setdefault(nombre, _Coleccion())


def _base_con_usuario():
    uid = ObjectId()
    base = _Base()
    base["users"] = _Coleccion([{"_id": uid, "wallet": {"local": 0.0, "usd": 5.0}}])
    return base, uid


def _acreditar(base, *args, **kwargs):
    with patch.object(wallet_repository, "get_database", return_value=base):
        return asyncio.run(WalletRepository().add_balance(*args, **kwargs))


def test_acredita_en_wallet_usd_y_deja_apunte():
    base, uid = _base_con_usuario()

    assert _acreditar(base, str(uid), 10.0, "stripe_recharge", "pi_123") is True

    usuario = base["users"].docs[0]
    assert usuario["wallet"] == {"local": 0.0, "usd": 15.0}
    assert "balance" not in usuario["wallet"]
    apunte = base["wallet_transactions"].docs[0]
    assert apunte["externalReference"] == "pi_123"
    assert apunte["toOwnerId"] == uid and apunte["currency"] == "usd" and apunte["amount"] == 10.0


def test_el_reintento_del_webhook_no_acredita_dos_veces():
    base, uid = _base_con_usuario()

    assert _acreditar(base, str(uid), 10.0, "stripe_recharge", "pi_123") is True
    assert _acreditar(base, str(uid), 10.0, "stripe_recharge", "pi_123") is False

    assert base["users"].docs[0]["wallet"]["usd"] == 15.0
    assert len(base["wallet_transactions"].docs) == 1


def test_no_acredita_a_un_usuario_que_no_existe_ni_importes_raros():
    base, _ = _base_con_usuario()

    assert _acreditar(base, str(ObjectId()), 10.0, "stripe_recharge", "pi_x") is False
    assert _acreditar(base, str(base["users"].docs[0]["_id"]), 0, "stripe_recharge", "pi_y") is False
    assert _acreditar(base, str(base["users"].docs[0]["_id"]), 5, "stripe_recharge", "pi_z", currency="eur") is False
    assert base["wallet_transactions"].docs == []
