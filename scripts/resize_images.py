"""
Responsive webp görsel oluşturucu.
Kullanım: python scripts/resize_images.py [--all] [dosya.webp ...]

PageSpeed'in 966x800 → 683x455 önerisi için -683w variant üretir.
Ayrıca sistemin mevcut -sm (480px) ve -md (683px) kuralına uygun variant da oluşturur.
"""

import sys
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Hata: Pillow kurulu değil. 'pip install pillow' komutunu çalıştırın.")
    sys.exit(1)

# Proje kök dizini
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "upload" / "images"

# Hedef genişlikler ve suffix eşlemeleri
SIZES = [
    (480, "-sm"),
    (683, "-md"),
    (966, "-lg"),
    (683, "-683w"),  # PageSpeed önerisi için ayrı variant
]

# Sadece -683w varyantı oluşturulacak dosyalar (PageSpeed raporu)
PRIORITY_FILES = [
    "img_efa7c60ce7aa.webp",
    "img_8cae621235ee.webp",
    "img_a34d3dbebcf4.webp",
    "img_3987859e187e.webp",
]


def resize_image(src_path: Path, target_width: int, suffix: str) -> Path | None:
    """Görseli hedef genişliğe orantılı olarak yeniden boyutlandırır."""
    # Dosya adını parçala: img_abc123.webp → img_abc123-md.webp
    stem = src_path.stem
    ext = src_path.suffix
    out_path = src_path.parent / f"{stem}{suffix}{ext}"

    # Zaten mevcutsa atla
    if out_path.exists():
        print(f"  [atlandı] {out_path.name} (zaten mevcut)")
        return out_path

    with Image.open(src_path) as img:
        orig_w, orig_h = img.size
        if orig_w <= target_width:
            print(f"  [atlandı] {src_path.name} → orijinal ({orig_w}px) ≤ hedef ({target_width}px)")
            return None

        # En-boy oranını koru
        ratio = target_width / orig_w
        new_h = int(orig_h * ratio)

        resized = img.resize((target_width, new_h), Image.LANCZOS)
        resized.save(out_path, "webp", quality=82, method=6)
        print(f"  [ok] {out_path.name}  ({orig_w}x{orig_h} → {target_width}x{new_h})")
        return out_path


def process_file(filepath: Path):
    """Tek bir dosya için tüm boyutları oluşturur."""
    print(f"\n→ {filepath.name}")
    for width, suffix in SIZES:
        resize_image(filepath, width, suffix)


def main():
    args = sys.argv[1:]

    if "--all" in args:
        # Upload klasöründeki tüm webp dosyaları
        files = sorted(UPLOAD_DIR.glob("img_*.webp"))
        # Zaten -sm/-md/-lg/-683w olan varyantları hariç tut
        files = [f for f in files if not any(
            s in f.stem for s in ("-sm", "-md", "-lg", "-683w", "_original")
        )]
        print(f"{len(files)} adet kaynak dosya bulundu.")
        for f in files:
            process_file(f)
    elif args:
        for name in args:
            p = UPLOAD_DIR / name if not Path(name).is_absolute() else Path(name)
            if p.exists():
                process_file(p)
            else:
                print(f"Dosya bulunamadı: {p}")
    else:
        # Varsayılan: PageSpeed'in bildirdiği öncelikli dosyalar
        print("PageSpeed öncelikli dosyalar için -683w variant oluşturuluyor...\n")
        for name in PRIORITY_FILES:
            p = UPLOAD_DIR / name
            if p.exists():
                resize_image(p, 683, "-683w")
            else:
                print(f"  [bulunamadı] {name} (üretim sunucusunda mevcut olabilir)")
        print("\nTüm dosyalar için çalıştırmak: python scripts/resize_images.py --all")


if __name__ == "__main__":
    main()
