#!/usr/bin/env python3
"""WIT Destek markalama scripti.

GitHub Actions derlemesi sirasinda, RustDesk kaynak kodu indirildikten hemen
sonra calisir. Kaynak kodu kalici olarak degistirmez; sadece o derlemeye ozel:
  - program adini "WIT-Destek" yapar (gorunen ad "WIT Destek"),
  - varsayilan sunucu adresini ve public key'i WIT sunucusuna cevirir,
  - ikonlari ve ana ekran logosunu WIT ile degistirir,
  - sirket adini WIT olarak yazar,
  - WIT_VARIANT=musteri ise programi "sadece gelen baglanti" moduna alir
    (baglan kutusu yok; sadece ID/sifre). teknisyen = tam surum.

Sunucu bilgileri depo degiskenlerinden gelir (Settings > Secrets and
variables > Actions > Variables):
  WIT_HOST  ornek: destek.wit.com.tr  veya  85.105.x.x
  WIT_KEY   sunucudaki id_ed25519.pub dosyasinin icerigi
"""
import os
import re
import shutil
import sys

APP_NAME = "WIT-Destek"      # ic ad: kurulum klasoru, servis, Mac paket adi (bosluk YASAK)
DISPLAY_NAME = "WIT Destek"  # sadece gorunen ad (exe bilgileri, Mac menu cubugu)
COMPANY = "Dunya Bilisim Teknolojileri"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WIT = os.path.join(ROOT, "wit")


def p(*parts):
    return os.path.join(ROOT, *parts)


def edit(path, pairs, required=True, regex=False):
    full = p(path)
    if not os.path.exists(full):
        if required:
            sys.exit(f"HATA: {path} bulunamadi")
        print(f"atlandi (yok): {path}")
        return
    with open(full, encoding="utf-8") as f:
        text = f.read()
    for old, new in pairs:
        if regex:
            text, n = re.subn(old, new, text)
        else:
            n = text.count(old)
            text = text.replace(old, new)
        if n == 0 and required:
            sys.exit(f"HATA: {path} icinde bulunamadi: {old!r}")
        print(f"{path}: {old!r} -> {n} degisiklik")
    with open(full, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main():
    host = os.environ.get("WIT_HOST", "").strip()
    key = os.environ.get("WIT_KEY", "").strip()
    if not host or not key:
        sys.exit(
            "HATA: WIT_HOST ve WIT_KEY depo degiskenleri bos. "
            "Settings > Secrets and variables > Actions > Variables kismina ekleyin."
        )

    # 1) Sunucu, key ve program adi (hbb_common)
    cfg = "libs/hbb_common/src/config.rs"
    edit(cfg, [
        ('&["rs-ny.rustdesk.com"]', f'&["{host}"]'),
        ('"OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw="', f'"{key}"'),
        ('APP_NAME: RwLock<String> = RwLock::new("RustDesk".to_owned())',
         f'APP_NAME: RwLock<String> = RwLock::new("{APP_NAME}".to_owned())'),
    ])

    # 2) Surum: musteri (sadece gelen baglanti, baglan kutusu yok) / teknisyen (tam)
    variant = os.environ.get("WIT_VARIANT", "musteri").strip() or "musteri"
    if variant not in ("musteri", "teknisyen"):
        sys.exit(f"HATA: WIT_VARIANT gecersiz: {variant!r}")
    if variant == "musteri":
        edit(cfg, [(
            "pub static ref HARD_SETTINGS: RwLock<HashMap<String, String>> = Default::default();",
            'pub static ref HARD_SETTINGS: RwLock<HashMap<String, String>> = '
            'RwLock::new(HashMap::from([("conn-type".to_owned(), "incoming".to_owned())]));',
        )])

    # 3) Exe bilgileri ve sirket adi
    for path in ("Cargo.toml", "libs/portable/Cargo.toml"):
        edit(path, [
            ('ProductName = "RustDesk"', f'ProductName = "{DISPLAY_NAME}"'),
            ('FileDescription = "RustDesk Remote Desktop"', f'FileDescription = "{DISPLAY_NAME}"'),
        ], required=False)
        edit(path, [(r"Purslane( Tech Pte\.)? Ltd\.?", COMPANY)], required=False, regex=True)
    edit("flutter/windows/runner/Runner.rc", [
        ('"RustDesk Remote Desktop"', f'"{DISPLAY_NAME}"'),
        ('"RustDesk"', f'"{DISPLAY_NAME}"'),
    ], required=False)
    edit("flutter/windows/runner/Runner.rc",
         [(r"Purslane( Tech Pte\.)? Ltd\.?", COMPANY)], required=False, regex=True)

    # 4) macOS: paket ve calistirilabilir dosya adi = APP_NAME
    #    (RustDesk /Applications/<APP_NAME>.app/Contents/MacOS/<APP_NAME> yolunu bekliyor)
    edit("flutter/macos/Runner/Configs/AppInfo.xcconfig", [
        ("PRODUCT_NAME = RustDesk", f"PRODUCT_NAME = {APP_NAME}"),
    ])
    edit("flutter/macos/Runner/Configs/AppInfo.xcconfig",
         [(r"Purslane( Tech Pte\.)? Ltd\.?", COMPANY)], required=False, regex=True)
    edit("flutter/macos/Runner.xcodeproj/project.pbxproj", [
        ("path = RustDesk.app;", f'path = "{APP_NAME}.app";'),
        ("/* RustDesk.app */", f"/* {APP_NAME}.app */"),
    ])
    edit("build.py", [
        ("Products/Release/RustDesk.app", f"Products/Release/{APP_NAME}.app"),
    ])
    edit("flutter/macos/Runner/Info.plist", [
        ("<key>CFBundleName</key>\n\t<string>$(PRODUCT_NAME)</string>",
         f"<key>CFBundleName</key>\n\t<string>{DISPLAY_NAME}</string>\n"
         f"\t<key>CFBundleDisplayName</key>\n\t<string>{DISPLAY_NAME}</string>"),
    ], required=False)

    # 5) Ikonlar
    icons = {
        "icon.ico": ["res/icon.ico", "flutter/windows/runner/resources/app_icon.ico"],
        "tray-icon.ico": ["res/tray-icon.ico"],
        "1024.png": ["res/icon.png", "res/mac-icon.png"],
        "32.png": ["res/32x32.png"],
        "64.png": ["res/64x64.png"],
        "128.png": ["res/128x128.png"],
        "256.png": ["res/128x128@2x.png"],
        "AppIcon.icns": ["flutter/macos/Runner/AppIcon.icns"],
        "icon.svg": ["flutter/assets/icon.svg", "flutter/windows/runner/resources/icon.svg"],
        "icon-256.png": ["flutter/assets/icon.png"],
        # Ana ekranda ID'nin ustunde gorunen buyuk logo (en fazla 300x60 gosterilir)
        "logo.png": ["flutter/assets/logo.png"],
        "logo_dark.png": ["flutter/assets/logo_dark.png"],
    }
    for src, dests in icons.items():
        s = os.path.join(WIT, src)
        if not os.path.exists(s):
            sys.exit(f"HATA: wit/{src} yok")
        for d in dests:
            shutil.copyfile(s, p(d))
            print(f"ikon: wit/{src} -> {d}")

    print(f"Markalama tamam: {APP_NAME} ({DISPLAY_NAME}) [{variant}] -> {host}")


if __name__ == "__main__":
    main()
