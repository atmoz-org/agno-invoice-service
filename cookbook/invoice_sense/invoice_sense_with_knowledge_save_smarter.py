import json
import os
import pdfplumber
from datetime import datetime
from agno.agent import Agent
from agno.storage.sqlite import SqliteStorage
from agno.models.openai import OpenAIChat
from typing import Optional

# Initialize SQLite storage for agent sessions
storage = SqliteStorage(
    table_name="agent_sessions",
    db_file="tmp/agent_memory.db"
)

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pdfplumber"""
    extracted_text = ""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} was not found.")
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            extracted_text += page.extract_text() or ""
    return extracted_text

def save_to_json(data: dict, base_name: str) -> None:
    """Save extracted data to a JSON file with a timestamped filename"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_name}_{timestamp}.json"
    with open(filename, "w") as json_file:
        json.dump(data, json_file, indent=4)
    print(f"Data saved to {filename}")

def parse_response(response_content: str) -> dict:
    """Parse the response content to extract structured invoice details"""
    details = {
        'line_items': []
    }
    try:
        lines = response_content.split('\n')
        for line in lines:
            clean_line = line.strip().replace('**', '')  # Remove markdown artifacts

            # Print each line for manual debugging
            print(f"Parsing line: {clean_line}")

            # Start parsing based on recognized key phrases
            if "Fakturanr" in clean_line:
                details['invoice_number'] = clean_line.split()[-1].strip()
            elif "Fakturadatum" in clean_line:
                details['invoice_date'] = clean_line.split()[-1].strip()
            elif "Totalt ATT BETALA" in clean_line:
                parts = clean_line.split()
                details['total_amount_due'] = parts[-2].replace(',', '').strip()
                details['currency'] = parts[-1].strip()
            elif "Kundnr" in clean_line:
                details['customer_number'] = clean_line.split()[-1].strip()
            elif "Vår referens" in clean_line:
                details['our_reference'] = clean_line.split()[-1].strip()
            elif "Er referens" in clean_line:
                details['your_reference'] = clean_line.split()[-1].strip()
            elif "Betalningsvillkor" in clean_line:
                details['payment_terms'] = ' '.join(clean_line.split()[1:3]).strip()
            elif "Leveransvillkor" in clean_line:
                details['delivery_terms'] = ' '.join(clean_line.split()[1:4]).strip()
            elif "Förfallodatum" in clean_line:
                details['due_date'] = clean_line.split()[-1].strip()
            elif "Leveranssätt" in clean_line:
                details['delivery_method'] = clean_line.split()[-1].strip()
            elif "Dröjsmålsränta" in clean_line:
                details['late_payment_interest'] = clean_line.split()[-1].replace('%', '').strip()
            elif "Fakturaperiod" in clean_line:
                details['service_period'] = ' '.join(clean_line.split()[-3:]).strip()
            elif "IBAN" in clean_line:
                details['iban'] = clean_line.split()[-1].strip()
            elif "BIC" in clean_line:
                details['bic'] = clean_line.split()[-1].strip()
            elif "Momsreg. nr" in clean_line:
                details['vat_registration_number'] = clean_line.split()[-1].strip()
            elif "E-post" in clean_line:
                details['email'] = clean_line.split()[-1].strip()
            elif "Webbadress" in clean_line:
                details['web_address'] = clean_line.split()[-1].strip()
            elif "Godkänd för F-skatt" in clean_line:
                details['tax_authorization'] = "Approved for F-tax"

            # Specific conditions for identifying line items
            elif any(keyword in clean_line for keyword in ["st", "enhet", "månadsavgift"]):
                details['line_items'].append(clean_line)

    except Exception as e:
        print(f"Error parsing response content: {e}")
    return details

def parse_response(response_content: str) -> dict:
    """Parse the response content to extract invoice details, including additional fields."""
    details = {}
    try:
        lines = response_content.split('\n')
        for line in lines:
            if "Invoice Number" in line:
                details['invoice_number'] = extract_field(line)
            elif "Invoice Date" in line:
                details['date'] = extract_field(line)
            elif "Total Amount" in line:
                details['total'] = normalize_currency(extract_field(line))
            elif "Currency" in line:
                details['invoice_currency'] = extract_field(line)
            elif "Your Reference" in line:
                details['your_reference'] = extract_field(line)
            elif "Payment Terms" in line:
                details['payment_terms'] = extract_field(line)
            elif "Delivery Method" in line:
                details['delivery_method'] = extract_field(line)
            elif "IBAN" in line:
                details['iban'] = extract_field(line)
            elif "VAT Registration Number" in line:
                details['vat_registration_number'] = extract_field(line)
            elif "Tax Authorization" in line:
                details['tax_authorization'] = extract_field(line)
    except Exception as e:
        print(f"Error parsing response content: {e}")
    return details


def extract_field(line: str) -> Optional[str]:
    """Extract and clean field value from a line."""
    return line.split(':', 1)[1].strip().replace('**', '')

def normalize_currency(amount_str: str) -> str:
    """Normalize the formatting of currency values."""
    return amount_str.replace(',', '')


def process_invoice(file_path: str):
    pdf_text = extract_text_from_pdf(file_path)

    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        storage=storage,
        description="Agent processes invoices to extract details directly from text.",
        markdown=True
    )

    # Run the agent to interpret text from the PDF including additional fields
    response = agent.run(
        f"Extract invoice details such as invoice number, date, total amount, currency, your reference, payment terms, delivery method, IBAN, VAT registration number, and tax authorization from the following text:\n{pdf_text}"
    )

    extracted_text = response.content if hasattr(response, 'content') else str(response)
    extracted_data = parse_response(extracted_text)
    save_to_json(extracted_data, os.path.splitext(os.path.basename(file_path))[0])

# Provide the absolute path to your local PDF file
process_invoice("test.pdf")