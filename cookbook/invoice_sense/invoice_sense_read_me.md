# Invoice Sense Streamlit App

This repository provides a Streamlit web application for extracting and cleaning structured invoice data using LLM agents.

---

## Prerequisites
- Python 3.8 or higher
- Valid API keys for any chosen providers (OpenAI, Anthropic, Google Gemini)
- (Optional) A Python virtual environment

## Environment Variables
- `OPENAI_API_KEY`: Your OpenAI API key for GPT models
- `ANTHROPIC_API_KEY`: Your Anthropic Claude API key
- `GOOGLE_API_KEY`: Your Google Gemini API key

Export them before running:
```bash
export OPENAI_API_KEY="<your_openai_key>"
export ANTHROPIC_API_KEY="<your_anthropic_key>"
export GOOGLE_API_KEY="<your_google_key>"
```

## Installation
Install core dependencies:
```bash
pip install -r requirements.txt
pip install agno openai streamlit
```

`requirements.txt` includes:
```
anthropic
google-genai
pdfplumber
watchdog
```

## Folder Structure
```
.
├── invoice_sense_read_me.md      # This instruction file
├── streamlit_app.py             # Main Streamlit application
├── codex_made.py                # Invoice extraction agent
├── codex_file_cleaner.py        # Invoice cleaning agent
├── switch_model.py              # Provider/model switcher
├── examples/invoice_examples/    # Few-shot snippet & JSON pairs
│   ├── example1.txt
│   └── example1.json
└── requirements.txt             # Core dependencies
```

## Running the App
```bash
streamlit run streamlit_app.py
```

## Usage
1. Upload PDF invoices via the sidebar.
2. Expand **⚙️ Advanced options** to configure extraction and cleaning agents independently.
3. Click **Run Extraction** for raw JSON, then **Run Cleaning** for validated JSON.
4. Download results with the buttons provided.
5. Tweak provider/model settings and re-run to compare outputs.

## Few-Shot Examples
Drop paired `.txt`/`.json` example files into `examples/invoice_examples/` to guide the extraction agent with real invoice formats.

## Troubleshooting & Logs
- Check `invoice_sense_error.log` for errors.
- Ensure correct environment variables are set.
- Add more examples in `examples/invoice_examples/` to cover edge cases.

---

Happy invoicing! 🚀