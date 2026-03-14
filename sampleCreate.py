import os
import urllib.request

# 이미지가 저장될 기준 폴더 경로
save_dir = "static/img/gstbook"

# 폴더가 없으면 생성
os.makedirs(save_dir, exist_ok=True)

# 생성할 샘플 데이터 구성
samples = [
    ("20260312", "01", ["001", "002", "003"], "FF5733", "FFFFFF"),
    ("20260313", "01", ["001", "002"], "33FF57", "000000"),
    ("20260314", "02", ["001", "002", "003", "004"], "3357FF", "FFFFFF"),
    ("20260315", "01", ["001"], "F333FF", "FFFFFF")
]

print(f"[{save_dir}] 폴더에 샘플 이미지 생성을 시작합니다...\n")

# 💡 403 에러 방지를 위한 User-Agent 헤더 추가 (브라우저인 척 속임)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

for date, event, seqs, bg, fg in samples:
    for seq in seqs:
        filename = f"gstb-{date}-{event}-{seq}.jpg"
        filepath = os.path.join(save_dir, filename)

        display_text = f"{date[:4]}-{date[4:6]}-{date[6:]}+/+{seq}"
        url = f"https://dummyimage.com/800x500/{bg}/{fg}&text={display_text}"

        try:
            # Request 객체를 생성하여 헤더를 포함시킨 후 다운로드
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response, open(filepath, 'wb') as out_file:
                out_file.write(response.read())
            print(f"✅ 생성 완료: {filename}")
        except Exception as e:
            print(f"❌ 생성 실패: {filename} ({e})")

print("\n🎉 모든 샘플 이미지 생성이 완료되었습니다!")
