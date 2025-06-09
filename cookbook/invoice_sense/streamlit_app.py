"""Streamlit web application for invoice extraction and cleaning using codex_made and codex_file_cleaner.

Usage:
    streamlit run streamlit_app.py
"""
import streamlit as st
import tempfile
import os
import json
import base64
import openai
import logging
import switch_model

# Configure error logging to file for later reference
logging.basicConfig(
    filename="invoice_sense_error.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s:%(message)s",
)

# Monkey-patch Anthropic client destructor to avoid AttributeError in SyncHttpxClientWrapper.__del__
try:
    import anthropic._base_client as _base

    def _safe_del(self):
        try:
            if getattr(self, "is_closed", True):
                return
            self.close()
        except Exception:
            pass

    _base.SyncHttpxClientWrapper.__del__ = _safe_del
except ImportError:
    pass

from codex_made import process_invoice
from codex_file_cleaner import process_cleaning

@st.cache_data(show_spinner=False)
def get_available_models():
    """Return the list of OpenAI models defined in switch_model.py."""
    return switch_model.get_openai_models()


@st.cache_data(show_spinner=False)
def get_anthropic_models():
    """Return the list of Anthropic Claude models defined in switch_model.py."""
    return switch_model.get_claude_models()

st.set_page_config(page_title="🧾 Invoice Parser", page_icon="📄", layout="wide")
st.title("🧾 Invoice Parser")
st.write("Use the sidebar to upload invoices and configure settings.")
st.markdown("---")
# Initialize session state for multiple files
if 'raws' not in st.session_state:
    st.session_state.raws = {}
if 'cleans' not in st.session_state:
    st.session_state.cleans = {}
if 'uploaded_names' not in st.session_state:
    st.session_state.uploaded_names = []

with st.sidebar:
    st.header("Upload & Settings")
    uploaded_files = st.file_uploader(
        "Choose PDF invoices", type="pdf", accept_multiple_files=True
    )
    with st.expander("⚙️ Advanced options", expanded=False):
        # Choose LLM provider and model
        providers = ["OpenAI", "Anthropic"]
        default_provider = st.session_state.get("provider", providers[0])
        provider_index = providers.index(default_provider) if default_provider in providers else 0
        st.selectbox("Provider", providers, index=provider_index, key="provider")
        if st.session_state.provider == "Anthropic":
            models = get_anthropic_models()
        else:
            models = get_available_models()
        default_model = st.session_state.get("model", models[0] if models else "")
        default_index = models.index(default_model) if default_model in models else 0
        st.selectbox("Model", models, index=default_index, key="model")
        # Configure the switch_model.agent based on the current selection
        switch_model.switch_model(st.session_state.provider, st.session_state.model)
        st.slider("Temperature", 0.0, 1.0, 0.0, key="temperature")
        st.number_input("Max tokens", min_value=256, max_value=8192, value=2048, key="max_tokens")
    st.markdown("---")
    overall_progress = st.progress(0)
if uploaded_files:
    # Reset state if uploads changed
    names = [file.name for file in uploaded_files]
    if st.session_state.uploaded_names != names:
        st.session_state.uploaded_names = names
        st.session_state.raws.clear()
        st.session_state.cleans.clear()

    # Batch progress setup
    total_steps = len(uploaded_files) * 2
    current_step = 0

    for idx, uploaded_file in enumerate(uploaded_files):
        with st.container():
            st.markdown("---")
            st.subheader(f"Invoice {idx+1}: {uploaded_file.name}")
            status_extract = st.empty()
            status_clean = st.empty()

            # Read PDF bytes
            try:
                pdf_bytes = uploaded_file.getvalue()
            except AttributeError:
                pdf_bytes = uploaded_file.read()
            b64 = base64.b64encode(pdf_bytes).decode('utf-8')

            # Setup layout: PDF preview | Raw JSON | Cleaned JSON
            col1, col2, col3 = st.columns([2, 3, 3])

            # PDF preview with lightbox-style expander
            with col1:
                st.download_button(
                    "Download PDF",
                    data=pdf_bytes,
                    file_name=uploaded_file.name,
                    mime="application/pdf",
                    key=f"download_pdf_{idx}",
                )
                exp_pdf = st.expander("📄 Preview PDF", expanded=False)
                exp_pdf.markdown(
                    f'<iframe src="data:application/pdf;base64,{b64}" '
                    f'width="100%" height="600px" type="application/pdf"></iframe>',
                    unsafe_allow_html=True,
                )

            # Extraction step
            raw_info = st.session_state.raws.get(idx)
            if not raw_info:
                status_extract.info("Extracting...")
                with st.spinner(f"Extracting {uploaded_file.name}..."):
                    tmp_dir = tempfile.mkdtemp()
                    pdf_path = os.path.join(tmp_dir, uploaded_file.name)
                    with open(pdf_path, "wb") as f:
                        f.write(pdf_bytes)
                    try:
                        raw_json_path = process_invoice(
                            pdf_path,
                            model=st.session_state.model,
                            provider=st.session_state.provider,
                        )
                        with open(raw_json_path, "r", encoding="utf-8") as f:
                            raw_data = json.load(f)
                        st.session_state.raws[idx] = {
                            "pdf_path": pdf_path,
                            "raw_json_path": raw_json_path,
                            "raw_data": raw_data,
                        }
                        status_extract.success("Extraction complete")
                        current_step += 1
                        overall_progress.progress(int(current_step / total_steps * 100))
                    except Exception as e:
                        # Log extraction errors for later debugging
                        st.session_state.raws[idx] = {"error": str(e)}
                        logging.exception(f"Extraction failed for invoice {uploaded_file.name}")
                        status_extract.error(f"Extraction failed: {e}")
                        continue

            raw_info = st.session_state.raws.get(idx)
            if raw_info.get("error"):
                continue

            # Raw JSON display and download
            with col2:
                exp_raw = st.expander("🔍 Raw JSON", expanded=False)
                exp_raw.json(raw_info["raw_data"])
                exp_raw.download_button(
                    "Download Raw JSON",
                    data=json.dumps(raw_info["raw_data"], indent=4),
                    file_name=os.path.basename(raw_info["raw_json_path"]),
                    mime="application/json",
                    key=f"download_raw_{idx}",
                )

            # Cleaning step
            if idx not in st.session_state.cleans:
                status_clean.info("Cleaning JSON...")
                with st.spinner("Cleaning JSON..."):
                    try:
                        cleaned_path = process_cleaning(
                            raw_info["raw_json_path"],
                            raw_info["pdf_path"],
                            model=st.session_state.model,
                            provider=st.session_state.provider,
                        )
                        with open(cleaned_path, "r", encoding="utf-8") as f:
                            cleaned_data = json.load(f)
                        st.session_state.cleans[idx] = {
                            "cleaned_json_path": cleaned_path,
                            "cleaned_data": cleaned_data,
                        }
                        status_clean.success("Cleaning complete")
                        current_step += 1
                        overall_progress.progress(int(current_step / total_steps * 100))
                    except Exception as e:
                        # Log cleaning errors for later debugging
                        logging.exception(f"Cleaning failed for invoice {uploaded_file.name}")
                        status_clean.error(f"Cleaning failed: {e}")

            # Cleaned JSON display, confidence, and download
            if idx in st.session_state.cleans:
                clean_info = st.session_state.cleans[idx]
                if clean_info["cleaned_data"].get("_confidence") is not None:
                    st.metric("Confidence", f"{clean_info['cleaned_data']['_confidence']:.2%}")
                with col3:
                    exp_clean = st.expander("✨ Cleaned JSON", expanded=False)
                    exp_clean.json(clean_info["cleaned_data"])
                    exp_clean.download_button(
                        "Download Cleaned JSON",
                        data=json.dumps(clean_info["cleaned_data"], indent=4),
                        file_name=os.path.basename(clean_info["cleaned_json_path"]),
                        mime="application/json",
                        key=f"download_clean_{idx}",
                    )

                    # Ignored fields reasons if any
                    ignored = clean_info["cleaned_data"].get("ignored_fields")
                    if ignored:
                        ignored_text = "\n".join(f"{item['field']}: {item['reason']}" for item in ignored)
                        st.text_area("Ignored Fields", value=ignored_text, height=120)

    # Sidebar summary metrics
    if st.session_state.cleans:
        with st.sidebar:
            st.markdown("---")
            st.header("Summary")
            total = len(st.session_state.uploaded_names)
            processed = len(st.session_state.cleans)
            # Compute average confidence, logging any errors
            try:
                avg_conf = (
                    sum(info["cleaned_data"].get("_confidence", 0)
                        for info in st.session_state.cleans.values())
                    / processed
                )
            except Exception as e:
                logging.exception("Failed to compute average confidence")
                avg_conf = 0.0
            st.metric("Invoices Processed", f"{processed}/{total}")
            st.metric("Avg Confidence", f"{avg_conf:.2%}")