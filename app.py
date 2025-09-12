"""
Dependencies (install once):
    pip install streamlit psutil plotly requests pandas

Run:
    streamlit run app.py
"""

import time
import datetime as dt
from collections import deque, defaultdict

import psutil
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ------------------ Page Config ------------------
st.set_page_config(
    page_title="System Resource Monitor",
    page_icon="⚡",
    layout="wide",
)

# ------------------ Helpers & API ------------------
@st.cache_data(show_spinner=False, ttl=300)
def get_system_info():
    """Fetch basic network info from ipinfo.io.
    Cached for 5 minutes to avoid rate limits.
    """
    try:
        res = requests.get("https://ipinfo.io/json", timeout=5)
        res.raise_for_status()
        data = res.json()
        return {
            "IP": data.get("ip", "N/A"),
            "City": data.get("city", "N/A"),
            "Region": data.get("region", "N/A"),
            "Country": data.get("country", "N/A"),
            "ISP": data.get("org", "N/A"),
        }
    except Exception:
        return {"IP": "N/A", "City": "N/A", "Region": "N/A", "Country": "N/A", "ISP": "N/A"}


def bytes_per_sec(prev, curr, elapsed):
    if elapsed <= 0:
        return 0.0, 0.0
    up = (curr.bytes_sent - prev.bytes_sent) / elapsed
    down = (curr.bytes_recv - prev.bytes_recv) / elapsed
    return max(up, 0.0), max(down, 0.0)


def format_rate(bps: float, unit: str) -> tuple[float, str]:
    """Convert bytes/sec to chosen unit and return value + label."""
    unit = unit.lower()
    if unit == "kb/s":
        return bps / 1024, "KB/s"
    if unit == "mb/s":
        return bps / (1024 * 1024), "MB/s"
    if unit == "mbps":  # megabits per second
        return (bps * 8) / (1024 * 1024), "Mbps"
    return bps, "B/s"


def prune_history(window_seconds: int):
    if not st.session_state.t_hist:
        return
    cutoff = dt.datetime.now() - dt.timedelta(seconds=window_seconds)
    while st.session_state.t_hist and st.session_state.t_hist[0] < cutoff:
        st.session_state.t_hist.popleft()
        st.session_state.cpu_hist.popleft()
        st.session_state.ram_hist.popleft()
        st.session_state.disk_hist.popleft()
        st.session_state.up_hist.popleft()
        st.session_state.down_hist.popleft()


def plot_timeseries(x, ys, names, title, ytitle):
    fig = go.Figure()
    for y, name in zip(ys, names):
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name=name))
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=ytitle,
        margin=dict(l=10, r=10, t=40, b=10),
        height=320,
    )
    return fig


def get_metrics_snapshot(net_unit: str) -> pd.DataFrame:
    """Return current history as DataFrame for export."""
    return pd.DataFrame({
        "time": list(st.session_state.t_hist),
        "cpu_percent": list(st.session_state.cpu_hist),
        "ram_percent": list(st.session_state.ram_hist),
        "disk_percent": list(st.session_state.disk_hist),
        f"upload_{net_unit}": [format_rate(v, net_unit)[0] for v in st.session_state.up_hist],
        f"download_{net_unit}": [format_rate(v, net_unit)[0] for v in st.session_state.down_hist],
    })

# ------------------ Sidebar ------------------
with st.sidebar:
    st.header("🌍 System Network Info (API)")
    sys_info = get_system_info()
    for k, v in sys_info.items():
        st.write(f"**{k}:** {v}")

    st.divider()
    st.header("⚙ Settings")
    refresh_rate = st.slider("⏱ Refresh Interval (seconds)", 0.5, 20.0, 10.0, 5.0)
    history_secs = st.slider("📊 History Window (seconds)", 15, 600, 60, 5)
    net_unit = st.selectbox("🌐 Network Unit", ["KB/s", "MB/s", "Mbps"], index=0)
    show_per_core = st.checkbox("Show per-core CPU usage", value=False)

    st.divider()
    run_col1, run_col2 = st.columns(2)
    with run_col1:
        start = st.button("▶️ Start", use_container_width=True)
    with run_col2:
        stop = st.button("⏹ Stop", use_container_width=True)

# ------------------ Session State ------------------
if "running" not in st.session_state:
    st.session_state.running = False
if "net_prev" not in st.session_state:
    st.session_state.net_prev = psutil.net_io_counters()
    st.session_state.time_prev = time.time()
if "cpu_hist" not in st.session_state:
    maxlen = 3000
    st.session_state.cpu_hist = deque(maxlen=maxlen)
    st.session_state.ram_hist = deque(maxlen=maxlen)
    st.session_state.disk_hist = deque(maxlen=maxlen)
    st.session_state.up_hist = deque(maxlen=maxlen)
    st.session_state.down_hist = deque(maxlen=maxlen)
    st.session_state.t_hist = deque(maxlen=maxlen)

# App usage tracking
if "apps_opened" not in st.session_state:
    st.session_state.apps_opened = defaultdict(int)
if "apps_start_time" not in st.session_state:
    st.session_state.apps_start_time = {}
if "apps_screen_time" not in st.session_state:
    st.session_state.apps_screen_time = defaultdict(float)
if "total_screen_time" not in st.session_state:
    st.session_state.total_screen_time = 0.0

# Toggle run/stop
if start:
    st.session_state.running = True
if stop:
    st.session_state.running = False

# ------------------ Header ------------------
st.title("⚡Real-Time System Resource Monitoring Dashboard")
subcols = st.columns(4)
with subcols[0]:
    st.metric("CPU Count", psutil.cpu_count(logical=True))
with subcols[1]:
    try:
        freq = psutil.cpu_freq()
        st.metric("CPU Freq (MHz)", f"{freq.current:.0f}")
    except Exception:
        st.metric("CPU Freq (MHz)", "N/A")
with subcols[2]:
    vm = psutil.virtual_memory()
    st.metric("Total RAM", f"{vm.total / (1024**3):.1f} GB")
with subcols[3]:
    du = psutil.disk_usage('/')
    st.metric("Disk Total", f"{du.total / (1024**3):.1f} GB")

st.markdown("---")

# ------------------ Layout Placeholders ------------------
row1 = st.columns((2, 2, 1), gap="large")
row2 = st.columns((2, 2), gap="large")

cpu_area = row1[0]
ram_area = row1[1]
_disk_area = row1[2]
net_area = row2[0]
_table_area = row2[1]

cpu_ph = cpu_area.empty()
ram_ph = ram_area.empty()
net_ph = net_area.empty()

# ------------------ Monitoring Loop ------------------
if st.session_state.running:
    now_ts = time.time()
    prev = st.session_state.net_prev
    prev_t = st.session_state.time_prev

    # System stats
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    curr = psutil.net_io_counters()
    up_bps, down_bps = bytes_per_sec(prev, curr, now_ts - prev_t)
    st.session_state.net_prev = curr
    st.session_state.time_prev = now_ts

    # Append histories
    now_dt = dt.datetime.now()
    st.session_state.t_hist.append(now_dt)
    st.session_state.cpu_hist.append(cpu)
    st.session_state.ram_hist.append(ram)
    st.session_state.disk_hist.append(disk)
    st.session_state.up_hist.append(up_bps)
    st.session_state.down_hist.append(down_bps)

    prune_history(history_secs)

    # ---------------- CPU Chart ----------------
    with cpu_area:
        if show_per_core:
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            x = list(range(1, len(per_core) + 1))
            fig = go.Figure(go.Bar(x=x, y=per_core, name="Core %"))
            fig.update_layout(title="🖥 CPU Usage per Core (%)", xaxis_title="Core", yaxis_title="%", height=320)
            cpu_ph.plotly_chart(fig, use_container_width=True)
        else:
            fig = plot_timeseries(
                list(st.session_state.t_hist),
                [list(st.session_state.cpu_hist)],
                ["CPU %"],
                "🖥 CPU Usage (%)",
                "%",
            )
            cpu_ph.plotly_chart(fig, use_container_width=True)

    # ---------------- RAM Chart ----------------
    with ram_area:
        fig = plot_timeseries(
            list(st.session_state.t_hist),
            [list(st.session_state.ram_hist)],
            ["RAM %"],
            "💾 RAM Usage (%)",
            "%",
        )
        ram_ph.plotly_chart(fig, use_container_width=True)

    # ---------------- Disk Gauge ----------------
    with _disk_area:
        gauge = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=disk,
                title={"text": "📂 Disk Usage (%)"},
                gauge={"axis": {"range": [0, 100]}},
            )
        )
        gauge.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(gauge, use_container_width=True)

    # ---------------- Network ----------------
    with net_area:
        up_v, up_label = format_rate(st.session_state.up_hist[-1], net_unit)
        down_v, down_label = format_rate(st.session_state.down_hist[-1], net_unit)
        st.subheader("🌐 Network Activity")
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("⬆ Upload", f"{up_v:.2f} {up_label}")
        kpi2.metric("⬇ Download", f"{down_v:.2f} {down_label}")

        up_series = [format_rate(v, net_unit)[0] for v in st.session_state.up_hist]
        down_series = [format_rate(v, net_unit)[0] for v in st.session_state.down_hist]
        fig = plot_timeseries(list(st.session_state.t_hist), [up_series, down_series], ["Upload", "Download"], "📡 Network Throughput", up_label)
        net_ph.plotly_chart(fig, use_container_width=True)

    # ---------------- Running Apps ----------------
    with _table_area:
        running_procs = {p.info["pid"]: p.info for p in psutil.process_iter(["pid", "name", "create_time"])}
        current_time = time.time()

        # Track apps open & screen time
        for pid, info in running_procs.items():
            name = info.get("name", "Unknown")
            if pid not in st.session_state.apps_start_time:
                st.session_state.apps_opened[name] += 1
                st.session_state.apps_start_time[pid] = current_time
            else:
                start_time = st.session_state.apps_start_time[pid]
                st.session_state.apps_screen_time[name] += current_time - start_time
                st.session_state.apps_start_time[pid] = current_time

        st.session_state.total_screen_time = sum(st.session_state.apps_screen_time.values())

        app_df = pd.DataFrame([
            {
                "Application": name,
                "Times Opened": count,
                "Screen Time (s)": f"{st.session_state.apps_screen_time[name]:.1f}",
            }
            for name, count in st.session_state.apps_opened.items()
        ])

        st.markdown("### 📝 Running Applications")
        st.dataframe(app_df.sort_values("Screen Time (s)", ascending=False), use_container_width=True)
        st.metric("⏳ Total Screen Time (s)", f"{st.session_state.total_screen_time:.1f}")

        # Export metrics
        df = get_metrics_snapshot(net_unit)
        csv = df.to_csv(index=False).encode()
        st.download_button("💾 Download CSV", data=csv, file_name="system_metrics.csv", mime="text/csv")

    time.sleep(float(refresh_rate))
    st.rerun()
else:
    st.info("Click **Start** to begin live monitoring. Adjust settings in the sidebar and click **Stop** anytime.")
