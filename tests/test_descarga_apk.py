"""GET /download/android elige el APK de la arquitectura pedida si está subido."""

from api.routes import APK_UNIVERSAL, clave_apk


def test_abi_con_apk_subido():
    assert clave_apk("arm64-v8a", lambda clave: True) == "apps/llego-arm64-v8a.apk"
    assert clave_apk("armeabi-v7a", lambda clave: True) == "apps/llego-armeabi-v7a.apk"


def test_sin_abi_o_sin_apk_de_esa_abi_da_el_universal():
    assert clave_apk(None, lambda clave: True) == APK_UNIVERSAL
    assert clave_apk("x86_64", lambda clave: True) == APK_UNIVERSAL
    assert clave_apk("arm64-v8a", lambda clave: False) == APK_UNIVERSAL
    assert clave_apk("../secreto", lambda clave: True) == APK_UNIVERSAL
