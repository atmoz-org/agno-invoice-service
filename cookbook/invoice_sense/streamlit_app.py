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
os.environ["GOOGLE_API_KEY"] = "{{api-key}}"

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

@st.cache_data(show_spinner=False)
def get_google_models():
    """Return the list of Google models defined in switch_model.py."""
    return switch_model.get_gemini_models()

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
if 'extracting' not in st.session_state:
    st.session_state.extracting = False
if 'cleaning' not in st.session_state:
    st.session_state.cleaning = False

with st.sidebar:
    st.header("Upload & Settings")
    uploaded_files = st.file_uploader(
        "Choose PDF invoices", type="pdf", accept_multiple_files=True,
        disabled=st.session_state.extracting,
    )
    with st.expander("⚙️ Advanced options", expanded=False):
        # Extraction agent settings
        st.subheader("Extraction Agent")
        providers = ["OpenAI", "Anthropic", "Google"]
        default_px = st.session_state.get("provider_extract", providers[0])
        px_index = providers.index(default_px) if default_px in providers else 0
        st.selectbox(
            "Provider (Extract)", providers, index=px_index,
            key="provider_extract", disabled=st.session_state.extracting,
        )
        if st.session_state.provider_extract == "Anthropic":
            models_ex = get_anthropic_models()
        elif st.session_state.provider_extract == "Google":
            models_ex = get_google_models()
        else:
            models_ex = get_available_models()
        default_me = st.session_state.get("model_extract", models_ex[0] if models_ex else "")
        me_index = models_ex.index(default_me) if default_me in models_ex else 0
        st.selectbox(
            "Model (Extract)", models_ex, index=me_index,
            key="model_extract", disabled=st.session_state.extracting,
        )
        st.slider(
            "Extraction Temperature", 0.0, 1.0, 0.0,
            key="temperature_extract", disabled=st.session_state.extracting,
        )
        st.number_input(
            "Extraction Max tokens", min_value=256, max_value=8192,
            value=2048,
            key="max_tokens_extract", disabled=st.session_state.extracting,
        )

        st.markdown("---")
        # Cleaning agent settings
        st.subheader("Cleaning Agent")
        default_pc = st.session_state.get("provider_clean", providers[0])
        pc_index = providers.index(default_pc) if default_pc in providers else 0
        st.selectbox(
            "Provider (Clean)", providers, index=pc_index,
            key="provider_clean", disabled=st.session_state.cleaning,
        )
        if st.session_state.provider_clean == "Anthropic":
            models_cl = get_anthropic_models()
        elif st.session_state.provider_clean == "Google":
            models_cl = get_google_models()
        else:
            models_cl = get_available_models()
        default_mc = st.session_state.get("model_clean", models_cl[0] if models_cl else "")
        mc_index = models_cl.index(default_mc) if default_mc in models_cl else 0
        st.selectbox(
            "Model (Clean)", models_cl, index=mc_index,
            key="model_clean", disabled=st.session_state.cleaning,
        )
        st.slider(
            "Cleaning Temperature", 0.0, 1.0, 0.0,
            key="temperature_clean", disabled=st.session_state.cleaning,
        )
        st.number_input(
            "Cleaning Max tokens", min_value=256, max_value=8192,
            value=2048,
            key="max_tokens_clean", disabled=st.session_state.cleaning,
        )
    st.markdown("---")
if uploaded_files:
    # Reset state if uploads changed
    names = [file.name for file in uploaded_files]
    if st.session_state.uploaded_names != names:
        st.session_state.uploaded_names = names
        st.session_state.raws.clear()
        st.session_state.cleans.clear()

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

            # Extraction button & Raw JSON display
            with col2:
                if st.button("Run Extraction", key=f"extract_btn_{idx}"):
                    st.session_state.extracting = True
                    status_extract.info("Extracting...")
                    with st.spinner(f"Extracting {uploaded_file.name}..."):
                        tmp_dir = tempfile.mkdtemp()
                        pdf_path = os.path.join(tmp_dir, uploaded_file.name)
                        with open(pdf_path, "wb") as f:
                            f.write(pdf_bytes)
                        try:
                            raw_json_path = process_invoice(
                                pdf_path,
                                model=st.session_state.model_extract,
                                provider=st.session_state.provider_extract,
                            )
                            with open(raw_json_path, "r", encoding="utf-8") as f:
                                raw_data = json.load(f)
                            st.session_state.raws[idx] = {
                                "pdf_path": pdf_path,
                                "raw_json_path": raw_json_path,
                                "raw_data": raw_data,
                                "error": None,
                            }
                            status_extract.success("Extraction complete")
                            st.session_state.extracting = False
                        except Exception as e:
                            st.session_state.raws[idx] = {"error": str(e)}
                            logging.exception(f"Extraction failed for invoice {uploaded_file.name}")
                            status_extract.error(f"Extraction failed: {e}")
                            st.session_state.extracting = False
                raw_info = st.session_state.raws.get(idx, {})
                if raw_info and not raw_info.get("error"):
                    exp_raw = st.expander("🔍 Raw JSON", expanded=False)
                    exp_raw.json(raw_info["raw_data"])
                    exp_raw.download_button(
                        "Download Raw JSON",
                        data=json.dumps(raw_info["raw_data"], indent=4),
                        file_name=os.path.basename(raw_info["raw_json_path"]),
                        mime="application/json",
                        key=f"download_raw_{idx}",
                    )

            # Cleaning button & Cleaned JSON display
            with col3:
                if raw_info and not raw_info.get("error"):
                    if st.button("Run Cleaning", key=f"clean_btn_{idx}"):
                        st.session_state.cleaning = True
                        status_clean.info("Cleaning JSON...")
                        with st.spinner("Cleaning JSON..."):
                            try:
                                cleaned_path = process_cleaning(
                                    raw_info["raw_json_path"],
                                    raw_info["pdf_path"],
                                    model=st.session_state.model_clean,
                                    provider=st.session_state.provider_clean,
                                )
                                with open(cleaned_path, "r", encoding="utf-8") as f:
                                    cleaned_data = json.load(f)
                                st.session_state.cleans[idx] = {
                                    "cleaned_json_path": cleaned_path,
                                    "cleaned_data": cleaned_data,
                                }
                                status_clean.success("Cleaning complete")
                                st.session_state.cleaning = False
                            except Exception as e:
                                logging.exception(f"Cleaning failed for invoice {uploaded_file.name}")
                                status_clean.error(f"Cleaning failed: {e}")
                                st.session_state.cleaning = False
                clean_info = st.session_state.cleans.get(idx, {})
                if clean_info:
                    if clean_info["cleaned_data"].get("_confidence") is not None:
                        st.metric("Confidence", f"{clean_info['cleaned_data']['_confidence']:.2%}")
                    exp_clean = st.expander("✨ Cleaned JSON", expanded=False)
                    exp_clean.json(clean_info["cleaned_data"])
                    exp_clean.download_button(
                        "Download Cleaned JSON",
                        data=json.dumps(clean_info["cleaned_data"], indent=4),
                        file_name=os.path.basename(clean_info["cleaned_json_path"]),
                        mime="application/json",
                        key=f"download_clean_{idx}",
                    )
                    ignored = clean_info["cleaned_data"].get("ignored_fields")
                    if ignored:
                        ignored_text = "\n".join(f"{item['field']}: {item['reason']}" for item in ignored)
                        st.text_area(
                            "Ignored Fields",
                            value=ignored_text,
                            height=120,
                            key=f"ignored_fields_{idx}",
                        )

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