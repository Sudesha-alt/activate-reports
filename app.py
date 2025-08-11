# app.py
# Streamlit app to compute call/WhatsApp engagement counts from a CSV/Excel upload
# pip install streamlit pandas openpyxl

import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Call & WhatsApp Report Summarizer", layout="centered")

st.title("📊 Activate Report Summarizer")

st.write(
    "Upload a CSV or Excel file that contains columns for **attempted calls**, **connected calls**, "
    "**sent WhatsApp (Sent WA)**, and **received WhatsApp (Received WA)**. "
    "Then map the columns below and get your counts."
)

# ---------- Helpers ----------
def normalize(s: str) -> str:
    """Lowercase, strip spaces/punct for easier matching."""
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())

def guess_column(columns, keywords):
    """
    Try to guess a column by checking normalized column name contains any keyword.
    keywords is a list of substrings to match.
    """
    norm_map = {c: normalize(c) for c in columns}
    for c, n in norm_map.items():
        if any(k in n for k in keywords):
            return c
    return None

def to_bool_series(s: pd.Series) -> pd.Series:
    """
    Convert a numeric/boolean/text column to a boolean indicating >0 or True-ish.
    - If numeric-able: True when value > 0
    - If boolean: use as-is
    - Else: True for strings like 'yes', 'true', 'y', '1'
    """
    if s.dtype == bool:
        return s.fillna(False)

    snum = pd.to_numeric(s, errors="coerce")
    if snum.notna().any():
        return (snum.fillna(0) > 0)

    str_vals = s.astype(str).str.strip().str.lower()
    true_set = {"yes", "y", "true", "t", "1", "connected", "done", "received", "delivered", "answer", "answered", "success"}
    return str_vals.isin(true_set)

# ---------- File upload ----------
file = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])

if file is None:
    st.info("Waiting for a file…")
    st.stop()

# Read file
try:
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

if df.empty:
    st.warning("Your file seems to be empty.")
    st.stop()

st.subheader("Step 1: Map your columns")

cols = list(df.columns)

# Attempt to guess typical variants
guess_call_attempted = guess_column(cols, [
    "attemptedcall", "callsattempted", "callattempt", "dialed", "callsdialed", "attempt", "outboundattempt"
])
guess_call_connected = guess_column(cols, [
    "connectedcall", "callsconnected", "callconnected", "callanswer", "answered", "connected", "successfulcall"
])
guess_wa_sent = guess_column(cols, [
    "sentwhatsapp", "sentwa", "whatsappsnt", "wasent", "wamsg", "msgsent", "whatsappsent", "wadelivered", "whatsappdelivered"
])
guess_wa_received = guess_column(cols, [
    "receivedwhatsapp", "receivedwa", "wareceived", "msgreceived", "whatsappreceived", "replied", "whatsappreply", "warcvd"
])

# Fallback soft search
if guess_call_attempted is None:
    for c in cols:
        n = normalize(c)
        if "call" in n and ("attempt" in n or "dial" in n or "made" in n):
            guess_call_attempted = c
            break
if guess_call_connected is None:
    for c in cols:
        n = normalize(c)
        if "call" in n and ("connect" in n or "answer" in n or "success" in n):
            guess_call_connected = c
            break
if guess_wa_sent is None:
    for c in cols:
        n = normalize(c)
        if ("wa" in n or "whatsapp" in n) and ("send" in n or "sent" in n or "deliver" in n or "attempt" in n):
            guess_wa_sent = c
            break
if guess_wa_received is None:
    for c in cols:
        n = normalize(c)
        if ("wa" in n or "whatsapp" in n) and ("receive" in n or "reply" in n or "rcvd" in n):
            guess_wa_received = c
            break

c1, c2 = st.columns(2)
with c1:
    col_call_attempted = st.selectbox(
        "Calls Attempted column", options=["-- select --"] + cols,
        index=(cols.index(guess_call_attempted) + 1) if guess_call_attempted in cols else 0
    )
    col_call_connected = st.selectbox(
        "Calls Connected column", options=["-- select --"] + cols,
        index=(cols.index(guess_call_connected) + 1) if guess_call_connected in cols else 0
    )
with c2:
    col_wa_sent = st.selectbox(
        "WhatsApp Sent (attempted) column", options=["-- select --"] + cols,
        index=(cols.index(guess_wa_sent) + 1) if guess_wa_sent in cols else 0
    )
    col_wa_received = st.selectbox(
        "WhatsApp Received (connected) column", options=["-- select --"] + cols,
        index=(cols.index(guess_wa_received) + 1) if guess_wa_received in cols else 0
    )

# Validate selections
required = {
    "Calls Attempted": col_call_attempted,
    "Calls Connected": col_call_connected,
    "WhatsApp Sent": col_wa_sent,
    "WhatsApp Received": col_wa_received,
}
missing = [name for name, sel in required.items() if sel == "-- select --"]
if missing:
    st.warning(f"Please select: {', '.join(missing)}")
    st.stop()

# ---------- Booleans ----------
try:
    call_attempted = to_bool_series(df[col_call_attempted])
    call_connected = to_bool_series(df[col_call_connected])
    wa_sent = to_bool_series(df[col_wa_sent])
    wa_received = to_bool_series(df[col_wa_received])
except Exception as e:
    st.error(f"Error interpreting columns: {e}")
    st.stop()

# By definition in this app:
# - WhatsApp attempted == message sent (wa_sent)
# - WhatsApp connected == message received (wa_received)
wa_attempted = wa_sent
wa_connected = wa_received

# ---------- Metrics ----------
m1 = (call_connected | wa_connected)
m2 = (call_connected & ~wa_connected)
m3 = (wa_connected & ~call_connected)
m4 = (~call_attempted)
m5 = (~wa_attempted)
m6 = (~call_attempted & ~wa_attempted)
m7 = (call_connected & wa_connected)
m8 = (call_connected & wa_sent & ~wa_received)
m9 = (~call_attempted & wa_attempted)
m10 = (call_attempted & ~wa_attempted)

# New segments:
# Total Leads (Unique)
total_leads = len(df)

# Duplicate Leads
duplicate_leads = df[df.duplicated(subset=['Phone Number'], keep=False)].shape[0]

# Metrics for Leads Connectivity
metrics = {
    "Leads Connected by Either WhatsApp or Call (Connectivity)": int(m1.sum()),
    "Only Connected on Calls": int(m2.sum()),
    "Only Connected on Calls and WhatsApp Also Got Attempted": int(m8.sum()),
    "Only Connected on WhatsApp": int(m3.sum()),
    "Leads Connected on Both WhatsApp and Call": int(m7.sum()),
    "Leads Where No WhatsApp and Calls Were Attempted (Call & WhatsApp = 0)": int(m6.sum()),
    "No Calls Attempted": int(m4.sum()),
    "No Calls Attempted but WhatsApp Attempted": int(m9.sum()),
    "No WhatsApp Attempted": int(m5.sum()),
    "No WhatsApp but Calls Attempted": int(m10.sum()),
    "Total Leads": total_leads,
    "Duplicate Leads": duplicate_leads,
}

# ---------- Tabular View of Hierarchy ----------
st.subheader("Stats")

segment_hierarchy = pd.DataFrame({
    "Hierarchy": [
        "Leads Connected by Either WhatsApp or Call (Connectivity)",
        "  Only Connected on Calls",
        "    Only Connected on Calls and WhatsApp Also Got Attempted",
        "  Only Connected on WhatsApp",
        "  Leads Connected on Both WhatsApp and Call",
        "Leads Where No WhatsApp and Calls Were Attempted (Call & WhatsApp = 0)",
        "  No Calls Attempted",
        "    No Calls Attempted but WhatsApp Attempted",
        "  No WhatsApp Attempted",
        "    No WhatsApp but Calls Attempted",
        "Total Leads",
        "Duplicate Leads"
    ],
    "Segment Count": [
        metrics["Leads Connected by Either WhatsApp or Call (Connectivity)"],
        metrics["Only Connected on Calls"],
        metrics["Only Connected on Calls and WhatsApp Also Got Attempted"],
        metrics["Only Connected on WhatsApp"],
        metrics["Leads Connected on Both WhatsApp and Call"],
        metrics["Leads Where No WhatsApp and Calls Were Attempted (Call & WhatsApp = 0)"],
        metrics["No Calls Attempted"],
        metrics["No Calls Attempted but WhatsApp Attempted"],
        metrics["No WhatsApp Attempted"],
        metrics["No WhatsApp but Calls Attempted"],
        metrics["Total Leads"],
        metrics["Duplicate Leads"]
    ]
})

st.dataframe(segment_hierarchy)

