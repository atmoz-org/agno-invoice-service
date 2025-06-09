"""
codex_made.py

A script to extract structured invoice information from a PDF and save it as JSON.
Supports both English and Swedish invoice labels, and uses Agno's ReasoningTools for enhanced parsing.
"""
import os
import sys
import json
from datetime import datetime
import pdfplumber
import subprocess

from agno.agent import Agent
from agno.storage.sqlite import SqliteStorage
from agno.tools.reasoning import ReasoningTools
import switch_model

# Initialize SQLite storage for agent sessions
storage = SqliteStorage(
    table_name="agent_sessions",
    db_file="tmp/agent_memory.db"
)

def extract_text_from_pdf(file_path: str) -> str:
    """Extract all text from a PDF file using pdfplumber, with page delimiters."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    text = ""
    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n=== Page {i}/{total_pages} ===\n{page_text}\n"
    return text

def save_to_json(data: dict, base_name: str) -> str:
    """Save extracted data to a timestamped JSON file within output/raw/ and return its path."""
    # Ensure output directory exists
    raw_dir = os.path.join("output", "raw")
    os.makedirs(raw_dir, exist_ok=True)
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_name}_{timestamp}.json"
    filepath = os.path.join(raw_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Saved extracted data to {filepath}")
    return filepath

def parse_response(response_content: str) -> dict:
    """
    Parse JSON response into structured invoice fields, capturing missing and additional fields.
    """
    try:
        data = json.loads(response_content)
    except json.JSONDecodeError:
        # Fallback: extract JSON block if present
        start = response_content.find("{")
        end = response_content.rfind("}")
        try:
            data = json.loads(response_content[start : end + 1])
        except Exception:
            data = {}

    expected_fields = [
        "invoice_number",
        "invoice_date",
        "due_date",
        "total_amount",
        "currency",
        "customer_number",
        "our_reference",
        "your_reference",
        "payment_terms",
        "delivery_terms",
        "delivery_method",
        "late_payment_interest",
        "service_period",
        "iban",
        "bic",
        "vat_registration_number",
        "email",
        "web_address",
        "tax_authorization",
        "line_items",
    ]
    details = {}
    additional_fields = {}
    ignored_fields = []

    for key in expected_fields:
        if key in data and data[key] not in (None, "", [], {}):
            details[key] = data[key]
        else:
            ignored_fields.append(
                {"field": key, "reason": "Not found or empty in the invoice response"}
            )

    # Collect any extra fields returned by the agent
    for key, value in data.items():
        if key not in expected_fields:
            additional_fields[key] = value

    if additional_fields:
        details["additional_fields"] = additional_fields
    if ignored_fields:
        details["ignored_fields"] = ignored_fields
    return details

def process_invoice(file_path: str, model: str = "gpt-4o", provider: str = "OpenAI") -> str:
    """
    Extract invoice info from PDF, parse with LLM, save to JSON, and return the JSON filename.

    Args:
        file_path: Path to the invoice PDF.
        model: LLM model identifier (e.g., OpenAI model or Claude model).
        provider: LLM provider to use ('OpenAI' or 'Anthropic').
    """
    # Clear previous agent memory to avoid carryover between runs
    try:
        import sqlite3

        conn = sqlite3.connect(storage.db_file)
        conn.execute(f"DELETE FROM {storage.table_name}")
        conn.commit()
        conn.close()
    except Exception:
        pass

    switch_model.switch_model(provider, model)

    # Step 1: Extract raw text from PDF
    pdf_text = extract_text_from_pdf(file_path)
    # Step 2: Scan PDF content with a dedicated agent to preserve layout
    scan_agent = Agent(
        model=switch_model.agent.model,
        storage=storage,
        tools=[ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True)],
        description=(
            "You are a brilliant PDF scanner who extracts the full invoice content, "
            "including tables and line items, preserving structure in plain text."
        ),
        markdown=False,
    )
    scan_prompt = f"Extract and preserve the complete invoice content below as plain text, retaining layout and tables.\n\nText:\n{pdf_text}"
    scan_resp = scan_agent.run(scan_prompt)
    scanned_text = scan_resp.content if hasattr(scan_resp, "content") else str(scan_resp)
    # Step 3: Parse structured fields from scanned text with a separate agent
    parse_agent = Agent(
        model=switch_model.agent.model,
        storage=storage,
        tools=[ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True)],
        description=(
            "You are a brilliant accountant AI, expert at extracting structured invoice data from any invoice format. "
            "Ignore any visual layout or structural formatting; extract all information fields regardless of their position or structure. "
            "Identify and extract all relevant fields, including invoice number, invoice date, due date, total amount, currency, customer and vendor references, line items, payment terms, tax details, and any additional invoice metadata. "
            "Provide the output as a JSON object with clearly labeled keys."
        ),
        markdown=False,
    )
    parse_prompt = (
        "You are an AI assistant specialized in extracting invoice data. "
        "Extract the specified fields below and present the result as a single valid JSON object. "
        "Use the exact key names listed, and if a field cannot be found, include it with a null value. "
        "Do not include any markdown or additional text.\n"
        "Fields to extract:\n"
        "- invoice_number (Invoice Number / Fakturanr)\n"
        "- invoice_date (Invoice Date / Fakturadatum, format YYYY-MM-DD)\n"
        "- due_date (Due Date / Förfallodatum, format YYYY-MM-DD)\n"
        "- total_amount (Total Amount / Totalt ATT BETALA)\n"
        "- currency\n"
        "- customer_number (Customer Number / Kundnr)\n"
        "- our_reference (Our Reference / Vår referens)\n"
        "- your_reference (Your Reference / Er referens)\n"
        "- payment_terms (Payment Terms / Betalningsvillkor)\n"
        "- delivery_terms (Delivery Terms / Leveransvillkor)\n"
        "- delivery_method (Delivery Method / Leveranssätt)\n"
        "- late_payment_interest (Late Payment Interest / Dröjsmålsränta)\n"
        "- service_period (Service Period / Fakturaperiod)\n"
        "- iban (IBAN)\n"
        "- bic (BIC)\n"
        "- vat_registration_number (VAT Registration Number / Momsreg. nr)\n"
        "- email (Email / E-post)\n"
        "- web_address (Web Address / Webbadress)\n"
        "- tax_authorization (Tax Authorization / Godkänd för F-skatt)\n"
        "- line_items (List of invoice line items, each with description, quantity, unit_price, and total_amount)\n"
        f"\nInvoice Text:\n{scanned_text}"
    )
    parse_resp = parse_agent.run(parse_prompt)
    resp_text = parse_resp.content if hasattr(parse_resp, "content") else str(parse_resp)
    # Parse and structure the fields into a dict
    data = parse_response(resp_text)
    # Log metadata: record which actual provider and model ID were used
    data["_provider"] = provider
    data["_model"] = switch_model.agent.model.id
    base = os.path.splitext(os.path.basename(file_path))[0]
    # Save raw JSON and return the filename for further processing
    raw_json = save_to_json(data, base)
    return raw_json

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python codex_made.py <invoice.pdf>")
        sys.exit(1)
    # Run extraction to produce raw JSON
    raw_json = process_invoice(sys.argv[1])
    # Automatically invoke the cleaner on the new JSON
    try:
        from codex_file_cleaner import process_cleaning
        process_cleaning(raw_json, sys.argv[1])
    except ImportError:
        subprocess.run([
            sys.executable,
            "codex_file_cleaner.py",
            raw_json,
            sys.argv[1]
        ], check=True)