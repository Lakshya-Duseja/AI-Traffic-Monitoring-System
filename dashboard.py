"""
Streamlit Dashboard — Smart Traffic Monitor
Run: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import os, time, tempfile
from PIL import Image
import io

from db_manager import init_db, get_violations, get_summary_stats, get_hourly_counts
from challan_generator import generate_challan

st.set_page_config(
    page_title="Smart Traffic Monitor",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.image("https://img.icons8.com/color/96/traffic-light.png", width=60)
st.sidebar.title("🚦 Traffic Monitor")
st.sidebar.markdown("---")
refresh_rate = st.sidebar.slider("Auto-refresh (seconds)", 2, 30, 5)
viol_filter  = st.sidebar.selectbox("Filter Violation Type",
    ["All","speeding","wrong_way","obstruction","tailgating","red_light"])
date_range   = st.sidebar.date_input("Date range",
    value=[datetime.today().date()-timedelta(days=7), datetime.today().date()])
st.sidebar.markdown("---")
st.sidebar.markdown("**Legend**")
st.sidebar.markdown("🔴 Speeding  🟣 Wrong-Way  🟡 Obstruction  🔵 Tailgating")

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_demo, tab1, tab2, tab3, tab4 = st.tabs([
    "🎬 Live Demo", "📊 Overview", "🚨 Violations", "📈 Analytics", "📄 Challans"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 0 — LIVE DEMO (video upload + real-time processing)
# ══════════════════════════════════════════════════════════════════════════════
with tab_demo:
    st.title("🎬 Live Demo — Upload & Analyse Video")
    st.markdown(
        "Upload any traffic video **or** click one of the demo buttons below. "
        "The system detects vehicles, estimates speed, flags violations and logs everything live."
    )

    col_up, col_cfg = st.columns([2, 1])
    with col_up:
        uploaded = st.file_uploader(
            "Upload a video file", type=["mp4","avi","mov","mkv"],
            help="Use any file from the demo_videos/ folder for best results"
        )
    with col_cfg:
        st.markdown("**Processing options**")
        skip_n  = st.selectbox("Process every N-th frame", [1,2,3,4], index=1,
                                help="Higher = faster preview")
        cam_id  = st.text_input("Camera ID label", value="CAM-DEMO")
        max_sec = st.number_input("Max seconds (0 = full video)", 0, 300, 0)
        run_btn = st.button("▶  Start Processing", type="primary",
                             disabled=(uploaded is None))

    # ── One-click demo buttons ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Quick-launch from demo_videos/ folder:**")
    demo_dir   = "demo_videos"
    demo_files = []
    if os.path.isdir(demo_dir):
        demo_files = sorted(f for f in os.listdir(demo_dir) if f.endswith(".mp4"))

    if demo_files:
        cols = st.columns(5)
        for i, fname in enumerate(demo_files):
            with cols[i % 5]:
                label = fname.replace(".mp4","").replace("_"," ").title()
                if st.button(label, key=f"demo_{i}", use_container_width=True):
                    st.session_state["demo_path"] = os.path.join(demo_dir, fname)
                    st.session_state["run_demo"]  = True
                    st.rerun()
    else:
        st.info("Run `python generate_demo_videos.py` to create demo videos.")

    st.markdown("---")

    # ── Resolve video source ──────────────────────────────────────────────────
    video_path = None
    tmp_file   = None

    if uploaded and run_btn:
        tmp_file   = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tmp_file.write(uploaded.read())
        tmp_file.flush()
        video_path = tmp_file.name
        st.session_state.pop("demo_path", None)
    elif st.session_state.get("run_demo") and "demo_path" in st.session_state:
        video_path = st.session_state["demo_path"]
        st.session_state.pop("run_demo", None)

    # ── Run processing ────────────────────────────────────────────────────────
    if video_path:
        st.success(f"Processing: `{os.path.basename(video_path)}`")

        frame_box  = st.empty()
        prog_bar   = st.progress(0, text="Starting…")
        viol_table = st.empty()
        stats_row  = st.empty()

        live_viols  = []
        frame_count = 0

        try:
            from video_processor import process_video
            import cv2

            max_frames = 0
            if max_sec > 0:
                cap_tmp = cv2.VideoCapture(video_path)
                fps_tmp = cap_tmp.get(cv2.CAP_PROP_FPS) or 25
                cap_tmp.release()
                max_frames = int(max_sec * fps_tmp)

            for frame_bytes, viols, pct in process_video(
                video_path, camera_id=cam_id,
                max_frames=max_frames, skip_frames=skip_n
            ):
                frame_count += 1
                live_viols.extend(viols)

                # Annotated frame
                img = Image.open(io.BytesIO(frame_bytes))
                frame_box.image(img, channels="RGB", use_container_width=True,
                                caption=f"Frame {frame_count}  |  Violations detected: {len(live_viols)}")

                prog_bar.progress(
                    min(int(pct), 100),
                    text=f"Processing… {pct:.0f}%  —  {len(live_viols)} violations found"
                )

                # Live violation table (last 8 rows)
                if live_viols:
                    cols_show = [c for c in
                                 ["track_id","violation","speed_kmph","fine_inr","plate","zone"]
                                 if c in live_viols[0]]
                    df_live = pd.DataFrame(live_viols[-8:])[cols_show]
                    viol_table.dataframe(df_live, use_container_width=True, hide_index=True)

                # Running metrics
                total_fine = sum(v.get("fine_inr", 0) for v in live_viols)
                with stats_row.container():
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Frames Processed", frame_count)
                    m2.metric("Violations Found",  len(live_viols))
                    m3.metric("Total Fines",       f"₹{total_fine:,}")

            prog_bar.progress(100, text="✅ Processing complete!")
            st.balloons()

            # ── Final summary ─────────────────────────────────────────────────
            if live_viols:
                st.markdown("### 📋 Final Violation Summary")
                df_final = pd.DataFrame(live_viols)
                if "violation" in df_final.columns:
                    c1, c2 = st.columns(2)
                    with c1:
                        vc = df_final["violation"].value_counts().reset_index()
                        vc.columns = ["Violation", "Count"]
                        fig = px.pie(vc, names="Violation", values="Count",
                                     title="Breakdown by Type",
                                     color_discrete_sequence=px.colors.qualitative.Set2,
                                     hole=0.4)
                        st.plotly_chart(fig, use_container_width=True)
                    with c2:
                        show_cols = [c for c in
                                     ["track_id","plate","violation","speed_kmph","fine_inr","zone"]
                                     if c in df_final.columns]
                        st.dataframe(df_final[show_cols],
                                     use_container_width=True, hide_index=True)
            else:
                st.info(
                    "No violations detected. Try a faster-moving video or lower "
                    "the speed limit in `config.py` → ZONES."
                )

        except ImportError as e:
            st.error(f"Missing dependency: {e}\nRun: pip install -r requirements.txt")
        except Exception as e:
            st.error(f"Processing error: {e}")
        finally:
            if tmp_file:
                try:
                    os.unlink(tmp_file.name)
                except Exception:
                    pass

    else:
        st.markdown(
            """
            <div style='text-align:center;padding:60px;background:#0e1117;
                        border-radius:12px;border:1px dashed #333;'>
                <h2 style='color:#555'>📹 Upload a video or click a demo button above</h2>
                <p style='color:#444'>Annotated frames will stream here in real time</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.title("Real-Time Traffic Overview")
    stats = get_summary_stats()

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total Violations",   stats["total_violations"])
    c2.metric("Today's Violations", stats["today_violations"])
    c3.metric("Avg Speed (km/h)",   f"{stats['avg_speed']:.1f}")
    c4.metric("Total Fines (INR)",  f"₹{stats['total_fines']:,}")
    c5.metric("Active Camera",      "CAM-01")
    st.markdown("---")

    if stats["by_type"]:
        df_pie = pd.DataFrame(list(stats["by_type"].items()), columns=["Violation","Count"])
        fig_pie = px.pie(df_pie, names="Violation", values="Count",
                         title="Violation Breakdown",
                         color_discrete_sequence=px.colors.qualitative.Set2, hole=0.45)
        fig_pie.update_traces(textinfo="percent+label")
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No violations logged yet. Use the 🎬 Live Demo tab to process a video.")

    hourly = get_hourly_counts()
    if hourly:
        df_h = pd.DataFrame(hourly)
        df_h["hr"] = df_h["hr"].astype(int)
        fig_h = px.bar(df_h, x="hr", y="avg_count",
                       labels={"hr":"Hour of Day","avg_count":"Avg Vehicle Count"},
                       title="Hourly Traffic Volume",
                       color="avg_count", color_continuous_scale="Blues")
        st.plotly_chart(fig_h, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — VIOLATIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.title("Violation Log")
    vt       = None if viol_filter == "All" else viol_filter
    df_start = str(date_range[0]) if len(date_range) > 0 else None
    df_end   = str(date_range[1]) if len(date_range) > 1 else None
    rows     = get_violations(limit=1000, violation_type=vt,
                              date_from=df_start, date_to=df_end)

    if rows:
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        col1,col2,col3 = st.columns(3)
        col1.metric("Filtered Count", len(df))
        col2.metric("Unique Plates",  df["plate"].nunique())
        col3.metric("Total Fines",    f"₹{df['fine_inr'].sum():,}")
        st.markdown("---")

        def color_violation(val):
            m = {"speeding":"background-color:#ffcccc",
                 "wrong_way":"background-color:#e6ccff",
                 "obstruction":"background-color:#fff0cc",
                 "tailgating":"background-color:#cce5ff"}
            return m.get(val, "")

        styled = df[["timestamp","track_id","plate","vtype","violation",
                      "speed_kmph","zone","fine_inr","camera_id"]].style.applymap(
            color_violation, subset=["violation"])
        st.dataframe(styled, use_container_width=True, height=450)
        csv = df.to_csv(index=False).encode()
        st.download_button("⬇ Download CSV", csv, "violations_export.csv","text/csv")
    else:
        st.info("No violations match the current filter.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.title("Traffic Analytics")
    rows_all = get_violations(limit=5000)

    if rows_all:
        df_all = pd.DataFrame(rows_all)
        df_all["timestamp"] = pd.to_datetime(df_all["timestamp"])
        df_all["date"] = df_all["timestamp"].dt.date
        df_all["hour"] = df_all["timestamp"].dt.hour

        col1, col2 = st.columns(2)
        with col1:
            daily = df_all.groupby("date").size().reset_index(name="count")
            fig_line = px.line(daily, x="date", y="count",
                               title="Daily Violation Trend", markers=True,
                               color_discrete_sequence=["#e63946"])
            st.plotly_chart(fig_line, use_container_width=True)
        with col2:
            fig_hist = px.histogram(df_all, x="speed_kmph", nbins=30,
                                    title="Speed Distribution",
                                    color_discrete_sequence=["#457b9d"])
            fig_hist.add_vline(x=60, line_dash="dash", line_color="red",
                               annotation_text="60 km/h limit")
            st.plotly_chart(fig_hist, use_container_width=True)

        pivot    = df_all.groupby(["hour","violation"]).size().unstack(fill_value=0)
        fig_heat = px.imshow(pivot.T, title="Violation Heatmap (Hour vs Type)",
                             color_continuous_scale="Reds",
                             labels=dict(x="Hour",y="Violation",color="Count"))
        st.plotly_chart(fig_heat, use_container_width=True)

        zone_fine = df_all.groupby("zone")["fine_inr"].sum().reset_index()
        fig_zone  = px.bar(zone_fine, x="zone", y="fine_inr",
                           title="Total Fines by Zone (INR)",
                           color="fine_inr", color_continuous_scale="Oranges")
        st.plotly_chart(fig_zone, use_container_width=True)
    else:
        st.info("No data yet — process a video in the 🎬 Live Demo tab first.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — CHALLANS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.title("Generate Challans")
    st.info("Select a violation row and generate a downloadable PDF challan.")

    rows_c = get_violations(limit=200)
    if rows_c:
        df_c = pd.DataFrame(rows_c)
        df_c["timestamp"] = pd.to_datetime(df_c["timestamp"])
        selected = st.dataframe(
            df_c[["id","timestamp","plate","violation","speed_kmph","fine_inr"]],
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            key="challan_table"
        )
        sel_rows = selected.selection.rows if selected.selection else []
        if sel_rows:
            row = df_c.iloc[sel_rows[0]].to_dict()
            st.write(f"**Selected:** #{row['id']} — {row['plate']} — {row['violation']}")
            if st.button("📄 Generate PDF Challan"):
                with st.spinner("Generating…"):
                    try:
                        path = generate_challan(row)
                        with open(path,"rb") as f:
                            st.download_button("⬇ Download Challan PDF", f,
                                               file_name=os.path.basename(path),
                                               mime="application/pdf")
                        st.success(f"Saved: {os.path.basename(path)}")
                    except Exception as e:
                        st.error(f"Failed: {e}. Run: pip install fpdf2")
    else:
        st.info("No violations yet. Process a video in the 🎬 Live Demo tab first.")

# ── Auto-refresh ───────────────────────────────────────────────────────────────
time.sleep(refresh_rate)
st.rerun()
