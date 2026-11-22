# WIT Destek

WIT (Dünya Bilişim Teknolojileri) uzak destek programı. [RustDesk](https://github.com/rustdesk/rustdesk) tabanlıdır, AGPL-3.0 lisanslıdır.

## Bu klasörde ne var?

| Dosya | Görevi |
|---|---|
| `brand.py` | Derleme sırasında program adını, sunucu adresini, key'i ve ikonları WIT'e çevirir |
| `icon.ico`, `tray-icon.ico` | Windows ikonları |
| `AppIcon.icns` | macOS ikonu |
| `*.png`, `icon.svg` | Uygulama içi ve genel ikonlar |

## Yeni sürüm derlemek

1. **Settings → Secrets and variables → Actions → Variables** kısmında şu iki değişken tanımlı olmalı:
   - `WIT_HOST`: WIT RustDesk sunucusunun adresi (örnek: `destek.wit.com.tr`)
   - `WIT_KEY`: Sunucudaki `id_ed25519.pub` dosyasının içeriği
2. **Actions → WIT Destek Build → Run workflow** ile derlemeyi başlatın.
3. Yaklaşık 1 saat sonra **Releases** sayfasında üç dosya hazır olur:
   - `WIT-Destek-windows-x86_64.exe`: Windows
   - `WIT-Destek-macos-aarch64.dmg`: Mac Apple Silicon (M1/M2/M3/M4)
   - `WIT-Destek-macos-x86_64.dmg`: Mac Intel

Sabit indirme linkleri (her zaman en son sürüm):

- https://github.com/witdestekwit-lab/wit-destek/releases/latest/download/WIT-Destek-windows-x86_64.exe
- https://github.com/witdestekwit-lab/wit-destek/releases/latest/download/WIT-Destek-macos-aarch64.dmg
- https://github.com/witdestekwit-lab/wit-destek/releases/latest/download/WIT-Destek-macos-x86_64.dmg

## RustDesk güncellemesi

GitHub'da depo sayfasındaki **Sync fork** düğmesiyle RustDesk'in son sürümü alınır, ardından derleme yeniden çalıştırılır. Sadece `wit/` klasörü ve `.github/workflows/wit-build.yml` WIT'e özeldir.
