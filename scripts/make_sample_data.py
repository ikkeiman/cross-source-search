"""合成データを作る。kintone の 3 アプリ分のレコード（JSON）と、ローカルフォルダ用のファイル（.md / .txt / .docx）。

すべて架空。Faker(ja_JP) とテンプレートで生成し、seed を固定して再現できるようにする。
使い方: python scripts/make_sample_data.py --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from faker import Faker

ROOT = Path(__file__).resolve().parents[1] / "sample_data"

TOPICS = [
    ("経費精算の締め日", "経費精算の締め日を毎月25日から月末に変更する"),
    ("在宅勤務の申請", "在宅勤務の申請を紙から電子申請に切り替える"),
    ("来客用駐車場", "来客用駐車場の予約をカレンダーで管理する"),
    ("社内ポータルの改修", "社内ポータルのお知らせ欄に検索窓を追加する"),
    ("備品の棚卸し", "備品の棚卸しを年2回から年1回にし、台帳をアプリで管理する"),
    ("新入社員研修", "新入社員向けのシステム研修を2日間から3日間に拡充する"),
    ("問い合わせ窓口", "部署ごとの問い合わせ窓口を一本化し、一次受付を当番制にする"),
    ("複合機の更新", "複合機のリース更新に合わせてスキャン保存先を見直す"),
    ("会議室の予約ルール", "会議室の予約は当日キャンセルを可視化し、空予約を減らす"),
    ("マニュアルの保管場所", "業務マニュアルの保管場所を共有フォルダに統一する"),
    ("議事録の書き方", "議事録は決定事項・担当・期限の3点を先頭に書く"),
    ("請求書の電子化", "受領した請求書を読み取りアプリで登録し、原本の保管期間を見直す"),
]


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(rid: int, updated: datetime, fields: dict[str, tuple[str, str]]) -> dict:
    r = {
        "$id": {"type": "__ID__", "value": str(rid)},
        "$revision": {"type": "__REVISION__", "value": "1"},
        "更新日時": {"type": "UPDATED_TIME", "value": iso(updated)},
        "作成日時": {"type": "CREATED_TIME", "value": iso(updated - timedelta(days=1))},
    }
    for code, (ftype, value) in fields.items():
        r[code] = {"type": ftype, "value": value}
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    fake = Faker("ja_JP")
    Faker.seed(args.seed)
    base = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

    # --- kintone 3 アプリ -----------------------------------------------------
    minutes = []
    for i in range(1, 31):
        topic, decision = rng.choice(TOPICS)
        dt = base + timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 8))
        minutes.append(
            rec(
                i,
                dt,
                {
                    "件名": ("SINGLE_LINE_TEXT", f"{topic}について（第{rng.randint(1, 5)}回）"),
                    "開催日": ("DATE", dt.strftime("%Y-%m-%d")),
                    "参加部署": (
                        "CHECK_BOX",
                        rng.sample(["総務", "営業", "情報システム", "経理", "人事"], k=2),
                    ),
                    "決定事項": (
                        "MULTI_LINE_TEXT",
                        f"{decision}。担当は{fake.last_name()}、期限は{(dt + timedelta(days=14)).strftime('%m月%d日')}。",
                    ),
                    "備考": (
                        "MULTI_LINE_TEXT",
                        rng.choice(
                            [
                                "次回に進捗を確認する",
                                "関連する手順書を更新する",
                                "対象部署へ周知する",
                                "",
                            ]
                        ),
                    ),
                },
            )
        )
    inquiries = []
    for i in range(1, 41):
        topic, _ = rng.choice(TOPICS)
        dt = base + timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 8))
        inquiries.append(
            rec(
                i,
                dt,
                {
                    "件名": ("SINGLE_LINE_TEXT", f"{topic}の手順が分からない"),
                    "分類": ("DROP_DOWN", rng.choice(["操作方法", "申請", "不具合", "要望"])),
                    "内容": (
                        "MULTI_LINE_TEXT",
                        f"{topic}について、どの画面から進めればよいか教えてほしい。{rng.choice(['先月から手順が変わったと聞いた', '過去のマニュアルが見つからない', '他部署では別のやり方をしている'])}。",
                    ),
                    "回答": (
                        "MULTI_LINE_TEXT",
                        rng.choice(
                            [
                                f"{topic}の手順書は共有フォルダの「手順書」にある。",
                                "担当から折り返し連絡する。",
                                "次回の説明会で案内する。",
                                "",
                            ]
                        ),
                    ),
                    "状態": ("RADIO_BUTTON", rng.choice(["受付", "対応中", "完了"])),
                },
            )
        )
    requests_ = []
    for i in range(1, 21):
        topic, decision = rng.choice(TOPICS)
        dt = base + timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 8))
        requests_.append(
            rec(
                i,
                dt,
                {
                    "件名": ("SINGLE_LINE_TEXT", f"{topic}の変更申請"),
                    "申請部署": (
                        "DROP_DOWN",
                        rng.choice(["総務", "営業", "情報システム", "経理", "人事"]),
                    ),
                    "概要": (
                        "MULTI_LINE_TEXT",
                        f"{decision}ため、運用の変更を申請する。概算の作業量は{rng.randint(2, 20)}時間。",
                    ),
                    "承認状況": ("RADIO_BUTTON", rng.choice(["申請中", "承認", "差戻し"])),
                },
            )
        )
    kintone = {
        "apps": [
            {"appId": "1", "name": "会議の議事録", "records": minutes},
            {"appId": "2", "name": "社内問い合わせ", "records": inquiries},
            {"appId": "3", "name": "運用変更の申請", "records": requests_},
        ]
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "kintone_records.json").write_text(
        json.dumps(kintone, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # --- ローカルフォルダのファイル ----------------------------------------------
    files = ROOT / "files"
    files.mkdir(exist_ok=True)
    for old in files.glob("*"):
        old.unlink()
    for i, (topic, decision) in enumerate(TOPICS[:8], start=1):
        body = (
            f"# {topic} 手順書\n\n"
            f"## 目的\n{decision}。\n\n"
            f"## 手順\n1. 社内ポータルから申請画面を開く\n2. 必要事項を入力して送信する\n3. 承認されたら通知が届く\n\n"
            f"## 注意\n{rng.choice(['締め日直前は処理が混み合う', '添付ファイルは PDF にする', '不明点は問い合わせ窓口へ'])}。\n"
        )
        (files / f"{i:02d}_{topic}_手順書.md").write_text(body, encoding="utf-8")
    for i, (topic, decision) in enumerate(TOPICS[8:11], start=9):
        (files / f"{i:02d}_{topic}_メモ.txt").write_text(
            f"{topic}\n{decision}。\n担当: {fake.last_name()}\n", encoding="utf-8"
        )
    try:
        import docx

        d = docx.Document()
        d.add_heading("請求書の電子化 運用ルール", level=1)
        d.add_paragraph(
            "受領した請求書は読み取りアプリで登録し、登録後の原本は3か月保管して廃棄する。"
        )
        d.add_paragraph("例外: 税務上の保存義務があるものは原本を7年保管する。")
        t = d.add_table(rows=2, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "項目", "期限"
        t.cell(1, 0).text, t.cell(1, 1).text = "登録", "受領から3営業日"
        d.save(files / "12_請求書の電子化_運用ルール.docx")
    except ImportError:
        pass
    n = sum(len(a["records"]) for a in kintone["apps"])
    print(f"kintone: 3 アプリ {n} レコード, files: {len(list(files.glob('*')))} 件 → {ROOT}")


if __name__ == "__main__":
    main()
