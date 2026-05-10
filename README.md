# MinpakuPropSearch

民泊向け物件を自動検索し、条件に合致した新着物件をメールで通知するツールです。

## 対応サイト

| サイト | 種別 |
|--------|------|
| [楽待](https://www.rakumachi.jp/) | 収益物件専門 |
| [SUUMO](https://suumo.jp/library/) | 収益物件 |
| [AtHome](https://www.athome.co.jp/) | 売りアパート・マンション |
| [HOME'S](https://www.homes.co.jp/) | 一棟アパート・マンション |

> **注意**: REINS（不動産流通機構）は宅地建物取引業者のみが利用できる非公開データベースのため、対応していません。

## セットアップ

### 1. リポジトリをフォーク/クローン

```bash
git clone https://github.com/<your-username>/MinpakuPropSearch.git
cd MinpakuPropSearch
```

### 2. GitHub Secrets の設定

リポジトリの **Settings → Secrets and variables → Actions** で以下を追加：

| Secret名 | 内容 |
|----------|------|
| `GMAIL_USER` | 送信元のGmailアドレス（例: `yourname@gmail.com`） |
| `GMAIL_APP_PASSWORD` | Gmailのアプリパスワード（[取得方法](#gmailアプリパスワードの取得)） |
| `NOTIFY_TO_EMAIL` | 通知先メールアドレス（省略時は`GMAIL_USER`と同じ） |

### 3. 検索条件の設定

`config.yaml` を編集して検索条件をカスタマイズ：

```yaml
search:
  areas:
    - 東京都
    - 大阪府
    - 京都府
  max_price: 50000000   # 5,000万円
  min_price: 3000000    # 300万円
  min_yield: 7.0        # 最低表面利回り(%)
  max_building_age: 40  # 最大築年数

evaluation:
  preferred_areas:
    - 新宿区
    - 渋谷区
  min_score: 50          # 通知する最低スコア(100点満点)
```

### 4. GitHub Actions の有効化

`.github/workflows/daily_search.yml` が **毎朝8時(JST)** に自動実行されます。  
手動実行は Actions タブ → **民泊物件 日次自動検索** → **Run workflow** から可能です。

## ローカル実行

```bash
pip install -r requirements.txt

# 通常実行（メール送信あり）
GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD=xxxx python main.py

# テスト実行（メール送信なし）
python main.py --dry-run

# 既見物件も含めて強制通知
python main.py --force
```

## スコアリング基準

物件を以下の基準で100点満点評価します：

| 項目 | 最大点 | 基準 |
|------|--------|------|
| 利回り | 40点 | 12%以上→40点、10%→30点、8%→20点 |
| 価格 | 20点 | 予算前半→20点、予算内→10点 |
| 築年数 | 20点 | 10年以内→20点、20年→15点、30年→10点 |
| エリア | 20点 | 優遇エリア→20点、その他→5点 |

## GmailアプリパスワードUの取得

1. [Googleアカウント](https://myaccount.google.com/) → **セキュリティ**
2. **2段階認証** を有効化
3. **アプリパスワード** → 「メール」「Windowsコンピュータ」で生成
4. 生成された16桁のパスワードを `GMAIL_APP_PASSWORD` に設定

## スクレイパーについて

- 各サイトの HTML 構造が変更された場合、スクレイパーの修正が必要になることがあります
- 過度なアクセスを避けるため、リクエスト間に 2 秒の待機を設けています
- 各サイトの利用規約に従ってご利用ください
