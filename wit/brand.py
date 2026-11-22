#!/usr/bin/env python3
"""WIT Destek markalama scripti.

GitHub Actions derlemesi sirasinda, RustDesk kaynak kodu indirildikten hemen
sonra calisir. Kaynak kodu kalici olarak degistirmez; sadece o derlemeye ozel:
  - program adini "WIT Destek" yapar,
  - varsayilan sunucu adresini ve public key'i WIT sunucusuna cevirir,
  - ikonlari WIT ikonlariyla degistirir,
  - sirket adini WIT olarak yazar.

Sunucu bilgileri depo degiskenlerinden gelir (Settings > Secrets and
variables > Actions > Variables):
  WIT_HOST  ornek: destek.wit.com.tr  veya  85.105.x.x
  WIT_KEY   sunucudaki id_ed25519.pub dosyasinin icerigi
"""
import os
import re
import shutil
import sys

APP_NAME = "WIT Destek"
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

    # 2) Windows reg komutlari: isimde bosluk oldugu icin anahtar yollarini tirnakla
    #    (rdgen projesindeki duzeltmenin aynisi)
    win = "src/platform/windows.rs"
    edit(win, [
        (r'reg add \{\} /f /v share_rdp', r'reg add \\"{}\\" /f /v share_rdp'),
        (r'reg (add|delete) HKEY_CLASSES_ROOT\\\\(\.?)\{ext\}((?:\\\\[A-Za-z]+)*) ',
         r'reg \1 \\"HKEY_CLASSES_ROOT\\\\\2{ext}\3\\" '),
        (r'reg add \{subkey\} ', r'reg add \\"{subkey}\\" '),
    ], regex=True)

    # 3) Exe bilgileri ve sirket adi
    for path in ("Cargo.toml", "libs/portable/Cargo.toml"):
        edit(path, [
            ('ProductName = "RustDesk"', f'ProductName = "{APP_NAME}"'),
            ('FileDescription = "RustDesk Remote Desktop"', f'FileDescription = "{APP_NAME}"'),
        ], required=False)
        edit(path, [(r"Purslane( Tech Pte\.)? Ltd\.?", COMPANY)], required=False, regex=True)
    edit("flutter/windows/runner/Runner.rc", [
        ('"RustDesk Remote Desktop"', f'"{APP_NAME}"'),
        ('"RustDesk"', f'"{APP_NAME}"'),
    ], required=False)
    edit("flutter/windows/runner/Runner.rc",
         [(r"Purslane( Tech Pte\.)? Ltd\.?", COMPANY)], required=False, regex=True)

    # 4) macOS: menu cubugu / Dock adi
    edit("flutter/macos/Runner/Info.plist", [
        ("<key>CFBundleName</key>\n\t<string>$(PRODUCT_NAME)</string>",
         f"<key>CFBundleName</key>\n\t<string>{APP_NAME}</string>\n"
         f"\t<key>CFBundleDisplayName</key>\n\t<string>{APP_NAME}</string>"),
    ], required=False)
    edit("flutter/macos/Runner/Configs/AppInfo.xcconfig",
         [(r"Purslane( Tech Pte\.)? Ltd\.?", COMPANY)], required=False, regex=True)

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
    }
    for src, dests in icons.items():
        s = os.path.join(WIT, src)
        if not os.path.exists(s):
            sys.exit(f"HATA: wit/{src} yok")
        for d in dests:
            shutil.copyfile(s, p(d))
            print(f"ikon: wit/{src} -> {d}")

    print(f"Markalama tamam: {APP_NAME} -> {host}")


if __name__ == "__main__":
    main()
