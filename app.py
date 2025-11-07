import os
import glob
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

FIXED_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Bl5O42AEf0g2Yal4_SnmouacMNMf0ruApAEMBxnRBC0/edit?hl=ja&gid=0#gid=0"
FIXED_WORKSHEET_NAME = "勤務表"


def get_credentials_path() -> str:
    json_files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "*.json")))
    if not json_files:
        raise FileNotFoundError("同一フォルダにサービスアカウントのJSONが見つかりませんでした。")
    return json_files[0]


@st.cache_resource(show_spinner=False)
def get_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]
    # Streamlit Cloud: st.secrets からサービスアカウント情報を取得
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])  # type: ignore[arg-type]
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            return gspread.authorize(creds)
    except Exception:
        # secrets 存在時でもフォーマット不備などであればローカルJSONにフォールバック
        pass

    # ローカル実行用: JSONファイルから認証
    credentials_path = get_credentials_path()
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    return gspread.authorize(creds)


def parse_first_query_value(params: dict) -> str | None:
    if not params:
        return None
    # 明示キーを優先
    if "user_id" in params:
        val = params.get("user_id")
        return val[0] if isinstance(val, list) else str(val)
    # 何か1つでもあれば先頭を採用
    key = next(iter(params))
    val = params[key]
    return val[0] if isinstance(val, list) else str(val)


def format_timedelta(td: pd.Timedelta) -> str:
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


st.set_page_config(page_title="勤務表ビューア", page_icon="📄", layout="wide")
st.title("勤務確認")

try:
    client = get_client()
    sh = client.open_by_url(FIXED_SHEET_URL)
    ws = sh.worksheet(FIXED_WORKSHEET_NAME)
    values = ws.get_all_values()
    if not values:
        st.info("シートにデータがありません。")
    else:
        # 期待カラム: A:ユーザーID, B:日付, C:出勤時刻, D:退勤時刻, E:コメント
        expected_cols = ["ユーザーID", "日付", "出勤時刻", "退勤時刻", "コメント"]
        # シート実データの列数に合わせて最大5列まで取り込む
        max_cols = min(5, max(len(r) for r in values))
        trimmed = [row[:max_cols] for row in values]
        df = pd.DataFrame(trimmed, columns=expected_cols[: max_cols])
        if not df.empty and (
            (str(df.iloc[0, 0]).strip() == "ユーザーID")
            or (str(df.iloc[0, 1]).strip() == "日付")
        ):
            df = df.iloc[1:].reset_index(drop=True)

        # クエリパラメータからユーザーIDを取得
        qp = st.query_params
        user_filter = parse_first_query_value(qp)
        if user_filter:
            df = df[df["ユーザーID"].astype(str) == str(user_filter)]
            st.caption(f"ユーザーIDフィルタ適用: {user_filter}")

        # 型変換
        df["日付_dt"] = pd.to_datetime(df["日付"], errors="coerce")
        start_td = pd.to_timedelta(df["出勤時刻"], errors="coerce")
        end_td = pd.to_timedelta(df["退勤時刻"], errors="coerce")

        # 勤務時間の算出（跨ぎ対応: 退勤 < 出勤 の場合は+1日）
        df["start_dt"] = df["日付_dt"] + start_td
        df["end_dt"] = df["日付_dt"] + end_td
        valid_mask = df["start_dt"].notna() & df["end_dt"].notna()
        cross_mask = valid_mask & (df["end_dt"] < df["start_dt"])
        df.loc[cross_mask, "end_dt"] = df.loc[cross_mask, "end_dt"] + pd.Timedelta(days=1)
        df.loc[valid_mask, "勤務時間_td"] = df.loc[valid_mask, "end_dt"] - df.loc[valid_mask, "start_dt"]
        df["勤務時間"] = df["勤務時間_td"].apply(lambda td: format_timedelta(td) if pd.notna(td) else "00:00:00")

        # 月選択UI（存在する月から選択）
        df_valid_date = df.dropna(subset=["日付_dt"]).copy()
        months = (
            df_valid_date["日付_dt"].dt.to_period("M").astype(str).dropna().unique().tolist()
        )
        months.sort()

        selected_month = None
        df_month = df_valid_date.copy()
        if months:
            default_idx = len(months) - 1  # 末尾=最新月
            selected_month = st.selectbox("集計対象の月", months, index=default_idx)
            df_month = df[df["日付_dt"].dt.to_period("M").astype(str) == selected_month]
        else:
            st.info("有効な日付が存在しないため、月選択ができません。")
            df_month = df.iloc[0:0].copy()

        # 表示用: 選択月の明細（B〜D列 + 算出勤務時間 + コメント）
        base_cols = ["日付", "出勤時刻", "退勤時刻", "勤務時間"]
        if "コメント" in df_month.columns:
            base_cols.append("コメント")
        display_df = df_month[base_cols].copy()
        st.subheader("明細")
        st.dataframe(display_df, use_container_width=True)

        # 選択月の合計勤務時間
        selected_sum_td = df_month["勤務時間_td"].dropna().sum()
        selected_sum_str = format_timedelta(selected_sum_td) if pd.notna(selected_sum_td) else "00:00:00"
        st.metric("選択月の合計勤務時間", selected_sum_str)

        # 全体の月次集計（参考）
        monthly = (
            df.dropna(subset=["日付_dt", "勤務時間_td"]) 
              .assign(月=lambda x: x["日付_dt"].dt.to_period("M").astype(str))
              .groupby("月", as_index=False)["勤務時間_td"].sum()
        )
        if not monthly.empty:
            monthly["合計勤務時間"] = monthly["勤務時間_td"].apply(format_timedelta)
            monthly_display = monthly[["月", "合計勤務時間"]]
            st.subheader("月次集計（全体の参考）")
            st.dataframe(monthly_display, use_container_width=True)
        else:
            st.subheader("月次集計（全体の参考）")
            st.info("集計対象データがありません。")

except Exception as e:
    st.error(f"読み込みに失敗しました: {e}")
    st.exception(e)
