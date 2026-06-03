import requests
import streamlit as st

st.set_page_config(
    page_title="Store Intelligence Dashboard",
    layout="wide"
)

st.title("Purplle Store Intelligence Dashboard")

store_id = st.text_input(
    "Store ID",
    "STORE_BLR_001"
)

try:

    metrics = requests.get(
        f"http://localhost:8000/stores/{store_id}/metrics"
    ).json()

    anomalies = requests.get(
        f"http://localhost:8000/stores/{store_id}/anomalies"
    ).json()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Visitors",
            metrics["unique_visitors"]
        )

    with col2:
        st.metric(
            "Queue Depth",
            metrics["queue_depth"]
        )

    with col3:
        st.metric(
            "Conversion",
            metrics["conversion_rate"]
        )

    st.subheader("Anomalies")

    st.json(anomalies)

except Exception as e:

    st.error(str(e))