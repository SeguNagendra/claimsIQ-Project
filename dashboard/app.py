
import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


st.set_page_config(
    page_title="ClaimIQ Analytics",
    page_icon="📊",
    layout="wide",
)

st.title("ClaimIQ Analytics Dashboard")

API_URL = os.getenv(
    "CLAIMIQ_API_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

if "token" not in st.session_state:
    st.session_state.token = None

# Login
if not st.session_state.token:
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        try:
            response = requests.post(
                f"{API_URL}/auth/token",
                data={
                    "username": username,
                    "password": password,
                },
                timeout=10,
            )

            if response.status_code == 200:
                st.session_state.token = (
                    response.json()["access_token"]
                )
                st.rerun()
            elif response.status_code == 401:
                st.error("Invalid username or password.")
            else:
                st.error(
                    f"Login failed: HTTP {response.status_code}"
                )
        except requests.RequestException:
            st.error("Cannot connect to the ClaimIQ API.")

    st.info("Sign in with an admin or reviewer account.")
    st.stop()

# Get analytics using the authenticated API
headers = {
    "Authorization": f"Bearer {st.session_state.token}"
}

if st.sidebar.button("Log out"):
    st.session_state.token = None
    st.rerun()

if st.sidebar.button("Refresh"):
    st.rerun()

try:
    response = requests.get(
        f"{API_URL}/analytics/summary",
        headers=headers,
        timeout=15,
    )

    if response.status_code == 401:
        st.session_state.token = None
        st.warning("Session expired. Please log in again.")
        st.rerun()

    if response.status_code == 403:
        st.error("Your account cannot access analytics.")
        st.stop()

    response.raise_for_status()
    data = response.json()

except requests.RequestException:
    st.error("Could not retrieve analytics from FastAPI.")
    st.stop()

# KPI cards
total = data.get("total_claims", 0)
assigned = data.get("assigned_claims", 0)
unassigned = max(total - assigned, 0)
amount = data.get("total_amount", 0)
average = data.get("average_amount", 0)

a, b, c = st.columns(3)
a.metric("Total claims", total)
b.metric("Assigned claims", assigned)
c.metric("Unassigned claims", unassigned)

d, e = st.columns(2)
d.metric("Total claimed amount", f"{amount:,.2f}")
e.metric("Average claim amount", f"{average:,.2f}")

# Status charts
st.subheader("Claims by status")

by_status = data.get("by_status", {})

if by_status:
    frame = pd.DataFrame([
        {
            "Status": status.replace("_", " ").title(),
            "Claims": count,
        }
        for status, count in by_status.items()
    ])

    left, right = st.columns(2)

    with left:
        st.plotly_chart(
            px.pie(
                frame,
                names="Status",
                values="Claims",
                hole=0.4,
                title="Status distribution",
            ),
            use_container_width=True,
        )

    with right:
        st.plotly_chart(
            px.bar(
                frame,
                x="Status",
                y="Claims",
                text="Claims",
                title="Claim count by status",
            ),
            use_container_width=True,
        )

    st.dataframe(frame, use_container_width=True, hide_index=True)
else:
    st.info("No claims are available yet.")
