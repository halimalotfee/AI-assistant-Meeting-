import streamlit as st
import requests

API_URL = "http://localhost:8000"

# =====================
# Page config
# =====================
st.set_page_config(
    page_title="Meeting Report Generator",
    layout="wide",
)

# =====================
# Custom CSS (SAFE)
# =====================
st.markdown("""
<style>
body { background-color: #F8FAFC; }

/* Titles */
.center-title {
    text-align: center;
    font-size: 42px;
    font-weight: 700;
    color: #2563EB;
    margin-bottom: 0.4rem;
}
.center-subtitle {
    text-align: center;
    color: #475569;
    font-size: 18px;
    margin-bottom: 2.5rem;
}

/* Cards */
.section-box {
    background: white;
    padding: 1.4rem;
    border-radius: 12px;
    border: 1px solid #E2E8F0;
    margin-bottom: 1.5rem;
}

/* Buttons */
button {
    background-color: #2563EB !important;
    color: white !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
button:hover { background-color: #1D4ED8 !important; }

/* Sliders */
div[data-testid="stSlider"] div[role="presentation"] { background-color: #DBEAFE !important; }
div[data-testid="stSlider"] div[role="presentation"] > div { background-color: #2563EB !important; }
div[data-testid="stSlider"] [role="slider"] {
    background-color: #2563EB !important; border: 2px solid #2563EB !important;
}
div[data-testid="stSlider"] span { color: #2563EB !important; }

/* Checkbox */
div[data-testid="stCheckbox"] svg { fill: #2563EB !important; stroke: #2563EB !important; }

/* File uploader label */
div[data-testid="stFileUploader"] label { display: none !important; }
</style>
""", unsafe_allow_html=True)

# =====================
# Header
# =====================
st.markdown("<div class='center-title'>Meeting Report Generator</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='center-subtitle'>"
    "Upload a meeting audio file to generate a full transcript and a structured meeting report "
    "(objectives, topics, decisions, action items)."
    "</div>",
    unsafe_allow_html=True
)

# =====================
# Sidebar
# =====================
with st.sidebar:
    st.header("⚙️ Settings")

    language_hint = st.selectbox("🌍 Language", ["auto", "en", "fr"], index=0)
    diarization = st.selectbox("Speaker segmentation", ["none", "alternate"])
    gap_threshold = st.slider("Pause threshold (seconds)", 0.2, 5.0, 1.0)
    max_speakers = st.slider("Max number of speakers", 1, 8, 4)
    export_pdf = st.checkbox("Export report as PDF", value=True)

    st.markdown("---")
    st.caption("Demo-oriented interface – AI calls can be mocked")

lang_to_send = language_hint.strip() if language_hint.strip() else "auto"

# =====================
# Audio upload
# =====================

st.markdown("### 🎧 Audio upload")

audio_file = st.file_uploader(
    "Upload audio",
    type=["wav", "mp3", "m4a"],
)

if audio_file:
    st.success(f"Loaded file: {audio_file.name}")

st.markdown("</div>", unsafe_allow_html=True)

# =====================
# Action buttons
# =====================
col1, col2 = st.columns(2)
with col1:
    run_transcription = st.button("▶ Run transcription", use_container_width=True)
with col2:
    run_report = st.button("📄 Generate meeting report", use_container_width=True)

# =====================
# Transcription results
# =====================
if run_transcription:
    if not audio_file:
        st.warning("Please upload an audio file first.")
    else:
        
        st.subheader("🗣️ Transcription")

        params = {
            "diarization": diarization,
            "gap_threshold": gap_threshold,
            "max_speakers": max_speakers,
            "language_hint": lang_to_send,
        }
        files = {
            "file": (
                audio_file.name,
                audio_file.getvalue(),
                audio_file.type or "audio/mpeg",
            )
        }

        with st.spinner("Transcribing audio..."):
            res = requests.post(
                f"{API_URL}/reports/transcribe",
                params=params,
                files=files,
                timeout=3600,
            )

        if not res.ok:
            st.error("Transcription failed. Please check API quota or backend.")
        else:
            data = res.json()
            transcript = data["transcript"]

            st.success(f"Detected language: {transcript.get('language', 'unknown')}")

            st.markdown("#### Full text")
            st.write(transcript.get("text", ""))

            st.markdown("#### Segments")
            for i, s in enumerate(transcript.get("segments", [])):
                speaker = s.get("speaker") or ""
                st.markdown(
                    f"**{i+1}. {speaker}** "
                    f"[{s.get('start',0):.2f}s → {s.get('end',0):.2f}s]  \n"
                    f"{s.get('text','')}"
                )

        st.markdown("</div>", unsafe_allow_html=True)

# =====================
# Meeting report results
# =====================
if run_report:
    if not audio_file:
        st.warning("Please upload an audio file first.")
    else:
        
        st.subheader("📄 Meeting report")

        files = {
            "file": (
                audio_file.name,
                audio_file.getvalue(),
                audio_file.type or "audio/mpeg",
            )
        }
        data = {
            "language_hint": lang_to_send,
            "diarization": diarization,
            "gap_threshold": str(gap_threshold),
            "export_pdf": str(export_pdf).lower(),
        }

        with st.spinner("Generating meeting report..."):
            res = requests.post(
                f"{API_URL}/reports/notes",
                files=files,
                data=data,
                timeout=3600,
            )

        if not res.ok:
            st.error("Report generation failed.")
        else:
            result = res.json()
            summary = result.get("summary", {})

            st.success("Report generated successfully.")

            st.markdown("#### Summary")
            st.write(summary.get("executive_summary"))

            st.markdown("#### Objectives")
            for i, obj in enumerate(summary.get("objectives", []), start=1):
                st.markdown(f"{i}. {obj}")

            st.markdown("#### Topics")
            for t in summary.get("topics", []):
                st.markdown(f"**{t.get('title','')}**")
                if t.get("description"):
                    st.write(t.get("description"))

            st.markdown("#### Decisions")
            for d in summary.get("decisions", []):
                st.markdown(f"- {d}")

            st.markdown("#### Action items")
            for a in summary.get("actions", []):
                st.markdown(
                    f"- **{a.get('owner','-')}**: {a.get('action','')} "
                    f"_(deadline: {a.get('due','-')})_"
                )

            st.markdown("#### Next steps")
            for ns in summary.get("next_steps", []):
                st.markdown(f"- {ns}")

            # Downloads
            st.markdown("#### Download exports")
            exports = result.get("exports", {})

            if exports.get("markdown_url"):
                md_res = requests.get(f"{API_URL}{exports['markdown_url']}")
                if md_res.ok:
                    st.download_button(
                        "Download Markdown",
                        md_res.content,
                        file_name="meeting-notes.md",
                        mime="text/markdown",
                    )

            if exports.get("pdf_url"):
                pdf_res = requests.get(f"{API_URL}{exports['pdf_url']}")
                if pdf_res.ok:
                    st.download_button(
                        "Download PDF",
                        pdf_res.content,
                        file_name="meeting-report.pdf",
                        mime="application/pdf",
                    )

        st.markdown("</div>", unsafe_allow_html=True)
