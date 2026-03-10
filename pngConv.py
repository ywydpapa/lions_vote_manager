import os
import sys
import argparse
from PIL import Image

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def make_unique_path(path):
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    index = 1
    while True:
        candidate = f"{base}_{index}{ext}"
        if not os.path.exists(candidate):
            return candidate
        index += 1


def convert_to_png(src_path, dst_path):
    with Image.open(src_path) as img:
        if img.mode in ("RGBA", "LA"):
            converted = img.convert("RGBA")
        else:
            converted = img.convert("RGBA")
        converted.save(dst_path, "PNG")


def collect_files(folder, recursive=False):
    files = []

    if recursive:
        for root, _, filenames in os.walk(folder):
            for name in filenames:
                files.append(os.path.join(root, name))
    else:
        for name in os.listdir(folder):
            full_path = os.path.join(folder, name)
            if os.path.isfile(full_path):
                files.append(full_path)

    return sorted(files)


def process_folder(input_dir, output_dir=None, recursive=False, skip_existing=False):
    if not os.path.isdir(input_dir):
        print(f"[ERROR] 입력 폴더가 존재하지 않습니다: {input_dir}")
        return 1

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    all_files = collect_files(input_dir, recursive=recursive)

    total = 0
    converted = 0
    skipped = 0
    errors = 0

    for src_path in all_files:
        ext = os.path.splitext(src_path)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            continue

        total += 1

        base_name = os.path.splitext(os.path.basename(src_path))[0]
        target_dir = output_dir if output_dir else os.path.dirname(src_path)
        dst_path = os.path.join(target_dir, f"{base_name}.png")

        if os.path.abspath(src_path) == os.path.abspath(dst_path):
            print(f"[SKIP] 이미 PNG 파일입니다: {src_path}")
            skipped += 1
            continue

        if os.path.exists(dst_path):
            if skip_existing:
                print(f"[SKIP] 대상 파일이 이미 존재합니다: {dst_path}")
                skipped += 1
                continue
            else:
                dst_path = make_unique_path(dst_path)

        try:
            convert_to_png(src_path, dst_path)
            converted += 1
            print(f"[OK] {src_path} -> {dst_path}")
        except Exception as e:
            errors += 1
            print(f"[ERROR] {src_path}: {e}")

    print("\n===== 완료 =====")
    print(f"입력 폴더: {input_dir}")
    print(f"출력 폴더: {output_dir if output_dir else '(입력 폴더와 동일)'}")
    print(f"전체 이미지: {total}")
    print(f"변환 성공: {converted}")
    print(f"스킵: {skipped}")
    print(f"에러: {errors}")

    return 0 if errors == 0 else 2


def parse_args():
    parser = argparse.ArgumentParser(description="특정 폴더의 이미지 파일을 PNG로 변환합니다.")
    parser.add_argument("--input", required=True, help="입력 폴더 경로")
    parser.add_argument("--output", help="출력 폴더 경로 (미지정 시 입력 폴더에 저장)")
    parser.add_argument("--recursive", action="store_true", help="하위 폴더까지 재귀적으로 처리")
    parser.add_argument("--skip-existing", action="store_true", help="이미 같은 이름의 PNG가 있으면 건너뜀")
    return parser.parse_args()


def main():
    args = parse_args()
    exit_code = process_folder(
        input_dir=args.input,
        output_dir=args.output,
        recursive=args.recursive,
        skip_existing=args.skip_existing,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

