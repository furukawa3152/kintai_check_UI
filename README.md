# kintai_check_UI

## 概要
Google スプレッドシートの「勤務表」を Streamlit で閲覧・集計する最小アプリです。

## 動作要件
- Python 3.13（同梱の `venv/` でも可）
- 依存: `requirements.txt`

## ローカル実行
```bash
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

同一フォルダにサービスアカウントJSONを1つ配置してください（`.gitignore`によりコミット対象外）。

## Streamlit Cloud へのデプロイ
1. リポジトリをGitHubにプッシュ
2. Streamlit Cloudで新規アプリを作成し、このリポジトリを選択
3. App settings → Secrets に、`secrets.example.toml` を参考に以下の形式で登録

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@...iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

アプリは `st.secrets["gcp_service_account"]` が存在する場合はそれを使用し、存在しない場合はローカルのJSONにフォールバックします。

## 使い方
- 固定URLのスプレッドシート、固定シート名「勤務表」を読み込みます。
- ブラウザのクエリ `?user_id=XXXX` でユーザーIDをフィルタ可能。
- 月を選択して明細を絞り込み、合計勤務時間を表示します。
