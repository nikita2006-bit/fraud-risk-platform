import os
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

API_URL = os.getenv("FRAUD_API_URL", "http://api:8000")

st.set_page_config(page_title="Fraud Risk UI", layout="wide")
st.title("Fraud Risk Platform — UI")

tab1, tab2, tab3 = st.tabs(["Score Transaction", "Scores (Recent/History)", "Ingest CSV"])

def status_from_score(risk_score: float) -> str:
    if risk_score is None:
        return "UNKNOWN"
    if risk_score >= 0.80:
        return "BLOCKED"
    if risk_score >= 0.50:
        return "REVIEW"
    return "OK"

def badge(status: str) -> str:
    # Streamlit markdown badge
    if status == "BLOCKED":
        return "🟥 **BLOCKED**"
    if status == "REVIEW":
        return "🟨 **REVIEW**"
    if status == "OK":
        return "🟩 **OK**"
    return "⬜ **UNKNOWN**"

# ---- TAB 1 ----
with tab1:
    st.subheader("Score a transaction")
    col1, col2, col3 = st.columns(3)
    with col1:
        account_id = st.text_input("account_id", value="C123")
        txn_type = st.selectbox("type", ["TRANSFER", "CASH_OUT", "PAYMENT", "CASH_IN", "DEBIT"])
    with col2:
        amount = st.number_input("amount", min_value=0.01, value=100.0, step=10.0)
        dest_id = st.text_input("dest_id", value="M456")
    with col3:
        ts = st.text_input("ts (ISO8601)", value=datetime.now(timezone.utc).isoformat())

    payload = {
        "account_id": account_id,
        "type": txn_type,
        "amount": float(amount),
        "dest_id": dest_id,
        "ts": ts,
    }

    if st.button("Score", type="primary"):
        try:
            r = requests.post(f"{API_URL}/score", json=payload, timeout=30)
            if r.status_code >= 400:
                st.error(f"API error {r.status_code}: {r.text}")
            else:
                data = r.json()
                st.success("Scored!")
                st.json(data)

                cols = st.columns(4)
                cols[0].metric("Decision", str(data.get("decision", "—")))
                cols[1].metric("Risk score", str(data.get("risk_score", "—")))
                cols[2].metric("Model", str(data.get("model_version", "—")))
                cols[3].metric("Latency (ms)", str(data.get("latency_ms", "—")))
        except Exception as e:
            st.error(f"Request failed: {e}")

# ---- TAB 2 ----
with tab2:
    st.subheader("Scores")

    st.caption(f"API: {API_URL}")

    mode = st.radio("View", ["Recent", "History (all)"], horizontal=True)

    col1, col2, col3 = st.columns([2, 2, 6])
    with col1:
        limit = st.slider("Rows", 10, 500, 100, 10)
    with col2:
        offset = st.number_input("Offset", min_value=0, value=0, step=100, disabled=(mode == "Recent"))
    with col3:
        if st.button("Refresh"):
            st.rerun()

    try:
        if mode == "Recent":
            r = requests.get(f"{API_URL}/scores/recent", params={"limit": limit}, timeout=30)
        else:
            r = requests.get(f"{API_URL}/scores/history", params={"limit": limit, "offset": int(offset)}, timeout=30)

        if r.status_code >= 400:
            st.error(f"API error {r.status_code}: {r.text}")
        else:
            items = r.json().get("items", [])
            df = pd.DataFrame(items)
            if not df.empty and "risk_score" in df.columns:
                df["status"] = df["risk_score"].apply(status_from_score)
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load scores: {e}")

# ---- TAB 3 ----
with tab3:
    st.subheader("Ingest CSV → Ingest + Score → show results")

    uploaded = st.file_uploader("Choose CSV", type=["csv"])
    preview_rows = st.slider("Preview rows", 5, 200, 20, 5)

    if uploaded is not None:
        try:
            df_preview = pd.read_csv(uploaded)
            st.write("Preview:")
            st.dataframe(df_preview.head(preview_rows), use_container_width=True)
        except Exception as e:
            st.error(f"Failed to preview CSV: {e}")

        uploaded.seek(0)

        if st.button("Upload → Ingest + Score", type="primary"):
            try:
                files = {"file": (uploaded.name, uploaded.getvalue(), "text/csv")}
                r = requests.post(
                    f"{API_URL}/ingest/csv",
                    params={"score_after": "true"},
                    files=files,
                    timeout=180,
                )

                if r.status_code >= 400:
                    st.error(f"API error {r.status_code}: {r.text}")
                else:
                    out = r.json()

                    # metrics
                    cols = st.columns(4)
                    cols[0].metric("Staged", out.get("staged_rows", "—"))
                    cols[1].metric("Inserted", out.get("inserted", "—"))
                    cols[2].metric("Duplicates", out.get("duplicates", "—"))
                    cols[3].metric("Scored", out.get("scored_rows", out.get("scored", "—")))

                    scored_ids = out.get("scored_ids", [])
                    if scored_ids:
                        # fetch just-scored items
                        rr = requests.post(f"{API_URL}/scores/by_ids", json={"ids": scored_ids}, timeout=30)
                        if rr.status_code >= 400:
                            st.warning(f"Could not load scored rows: {rr.status_code}: {rr.text}")
                        else:
                            items = rr.json().get("items", [])
                            df_scored = pd.DataFrame(items)

                            st.markdown("### Just scored (newest on top)")
                            if not df_scored.empty and "risk_score" in df_scored.columns:
                                df_scored = df_scored.sort_values(by="created_at", ascending=False, errors="ignore")
                                df_scored["status"] = df_scored["risk_score"].apply(status_from_score)

                                # Show top cards grouped by status
                                for status in ["BLOCKED", "REVIEW", "OK"]:
                                    sub = df_scored[df_scored["status"] == status]
                                    if sub.empty:
                                        continue
                                    st.markdown(f"#### {badge(status)}  ({len(sub)})")
                                    st.dataframe(sub, use_container_width=True)

                            else:
                                st.dataframe(df_scored, use_container_width=True)
                    else:
                        st.info("No new scores were produced (maybe all were duplicates or already scored).")

                    st.divider()
                    if st.button("Go to Scores tab (refresh)"):
                        st.session_state["__refresh_scores__"] = True
                        st.rerun()

            except Exception as e:
                st.error(f"Upload failed: {e}")