"""
codex_file_cleaner.py

An Agno-based agent script to validate and clean a previously extracted invoice JSON file.

Usage:
    python codex_file_cleaner.py <raw_json_file> <invoice_pdf_file>

This script loads the raw JSON produced by codex_made.py and the original PDF,
prompts an LLM to correct data types, format dates, remove empty fields, and fix
any discrepancies based on the invoice text. The cleaned JSON is written to
<raw_json_basename>_cleaned.json.
"""
import os
import sys
import json
import re
import pdfplumber

from agno.agent import Agent
from agno.storage.sqlite import SqliteStorage
import switch_model
from agno.models.openai import OpenAIChat
from agno.tools.reasoning import ReasoningTools
from agno.models.anthropic import Claude
from agno.models.google import Gemini


# Initialize SQLite storage for agent sessions
storage = SqliteStorage(
    table_name="agent_sessions",
    db_file="tmp/agent_memory.db"
)

def extract_text_from_pdf(file_path: str) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text()
            if txt:
                text += txt + "\n"
    return text

def load_json(file_path: str) -> dict:
    """Load JSON data from a file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_cleaned_json(data: dict, raw_json_path: str) -> str:
    """Save cleaned JSON in output/cleaned/ with '_cleaned' suffix and return its path."""
    # Ensure cleaned output directory exists
    cleaned_dir = os.path.join("output", "cleaned")
    os.makedirs(cleaned_dir, exist_ok=True)
    base = os.path.basename(raw_json_path)
    name, _ = os.path.splitext(base)
    cleaned_name = f"{name}_cleaned.json"
    cleaned_path = os.path.join(cleaned_dir, cleaned_name)
    with open(cleaned_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Cleaned JSON saved to {cleaned_path}")
    return cleaned_path

def extract_json_block(text: str) -> str:
    """Extract JSON object from a text block, removing code fences if present."""
    # Look for ```json ... ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Fallback: strip any ``` fences
    text = re.sub(r"```[\s\S]*?```", '', text)
    return text.strip()

def sanitize_numeric_fields(data, convert_numbers: bool = True):
    """
    Normalize numeric-like string values by stripping common thousands separators.
    If convert_numbers is True, also convert pure-digit (with optional single decimal) strings to int or float.
    Thousands separators such as commas, spaces, and apostrophes are removed and not treated as decimal separators.
    A single decimal point is preserved if present and only converted when convert_numbers is True.
    """
    # Preserve existing numeric values
    if isinstance(data, (int, float)):
        return data
    # pattern matches strings of digits and common separators (comma, dot, apostrophe, space)
    sep_pattern = re.compile(r'^-?[\d\.,\s\']+$')
    if isinstance(data, dict):
        return {k: sanitize_numeric_fields(v, convert_numbers) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_numeric_fields(v, convert_numbers) for v in data]
    if isinstance(data, str):
        # strip thousands separators
        if sep_pattern.match(data):
            s = re.sub(r"[,\s']", "", data)
        else:
            s = data
        # convert to numeric types only when requested
        if convert_numbers and re.fullmatch(r'-?\d+(\.\d+)?', s):
            try:
                return float(s) if '.' in s else int(s)
            except ValueError:
                pass
        return s

def compute_rule_confidence(data: dict) -> float:
    """
    Compute a simple rule-based confidence score based on presence and validity
    of key invoice fields.
    """
    score = 0
    checks = 0
    # Invoice date check (YYYY-MM-DD)
    checks += 1
    inv_date = data.get("invoice_date")
    if isinstance(inv_date, str) and re.match(r"\d{4}-\d{2}-\d{2}$", inv_date):
        score += 1
    # Invoice number check
    checks += 1
    if data.get("invoice_number"):
        score += 1
    # Total amount check (number and >0)
    checks += 1
    total = data.get("total_amount")
    if isinstance(total, (int, float)) and total > 0:
        score += 1
    # Currency presence check
    checks += 1
    if data.get("currency"):
        score += 1
    # Line items check
    checks += 1
    items = data.get("line_items")
    if isinstance(items, list) and items:
        score += 1
    return score / checks if checks else 0.0

def process_cleaning(raw_json_path: str, pdf_path: str, model: str = "gpt-4o", provider: str = "OpenAI") -> str:
    """
    Run the cleaning agent on the raw JSON and PDF, then save and return the cleaned JSON path.

    Args:
        raw_json_path: Path to the raw JSON file.
        pdf_path: Path to the original invoice PDF.
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

    # Load inputs
    raw_data = load_json(raw_json_path)
    pdf_text = extract_text_from_pdf(pdf_path)

    # Determine which chat model class to use based on provider
    if provider.lower() == "anthropic":
        try:
            agent = Agent(
                model=Claude(id=model),
                storage=storage,
                tools=[ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True)],
                description="Clean and validate extracted invoice JSON against original PDF text.",
                markdown=True,
            )
        except ImportError:
            raise ImportError(
                "Anthropic support is not available. Please install 'anthropic' and enable Anthropic in agno."
            )
    elif provider.lower() == "google":
        try:
            agent = Agent(
                model=Gemini(id=model),
                storage=storage,
                tools=[ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True)],
                description="Clean and validate extracted invoice JSON against original PDF text.",
                markdown=True,
            )
        except ImportError:
            raise ImportError(
                "Gemini support is not available. Please install 'google' and enable Anthropic in agno."
            )
    else:
        agent = Agent(
                model=OpenAIChat(id=model),
                storage=storage,
                tools=[ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True)],
                description="Clean and validate extracted invoice JSON against original PDF text.",
                markdown=True,
            )
    # Initialize the agent with reasoning tools


    # Build cleaning prompt and ask for self-evaluated confidence
    prompt = (
        "You are a JSON data validator and cleaner. "
        "Given the raw invoice JSON and the original invoice text, ensure the following:\n"
        "1. Numeric fields are proper numbers (no separators). Remove all thousands separators such as commas, spaces, and apostrophes (e.g., '1 234', '1,234', \"1'234\"); do not interpret them as decimal separators. Preserve a single decimal point if present.\n"
        "2. Date fields (invoice_date, due_date) are formatted as YYYY-MM-DD.\n"
        "3. Remove any keys with empty or null values.\n"
        "4. Correct any obvious mismatches based on the invoice text.\n"
        "After cleaning, provide your confidence in the cleaned data's accuracy as a float "
        "between 0.0 and 1.0.\n"
        "Respond with a single JSON object with two keys: `cleaned_data` (the cleaned invoice JSON object) "
        "and `confidence` (the confidence score). Do not include any additional text or markdown.\n\n"
        "Raw JSON:\n```json\n"
        f"{json.dumps(raw_data, indent=4)}\n```"
        "\nInvoice Text:\n"
        f"{pdf_text}"
    )

    # Run the agent to clean JSON
    response = agent.run(prompt)
    resp_text = response.content if hasattr(response, 'content') else str(response)

    # Extract JSON block and parse the cleaned data and self-evaluation
    json_block = extract_json_block(resp_text)
    try:
        result = json.loads(json_block)
    except json.JSONDecodeError as e:
        print("Failed to parse cleaned JSON with confidence:", e)
        print("Agent response was:\n", resp_text)
        sys.exit(1)

    llm_conf = result.get("confidence")
    raw_cleaned = result.get("cleaned_data") or {}

    # Remove separators but leave numeric strings intact until final cleaning pass
    sanitized_cleaned = sanitize_numeric_fields(raw_cleaned, convert_numbers=False) or {}

    rule_conf = compute_rule_confidence(sanitized_cleaned)
    if not isinstance(rule_conf, (int, float)):
        rule_conf = 0.0

    # Average only the numeric confidences (ignore None)
    confs = []
    if isinstance(llm_conf, (int, float)):
        confs.append(llm_conf)
    if isinstance(rule_conf, (int, float)):
        confs.append(rule_conf)
    final_conf = sum(confs) / len(confs) if confs else 0.0
    sanitized_cleaned["_confidence"] = final_conf

    # Merge back any fields dropped or nullified by LLM, preserving original raw_data values
    merged = raw_data.copy()
    for key, val in sanitized_cleaned.items():
        if val is not None:
            merged[key] = val

    # Finally sanitize merged data to convert any raw_data numeric strings
    finalized = sanitize_numeric_fields(merged)
    # Log metadata: record which actual provider and model ID were used
    finalized["_provider"] = provider
    finalized["_model"] = switch_model.agent.model.id

    # Save cleaned JSON and return its path
    cleaned_path = save_cleaned_json(finalized, raw_json_path)
    return cleaned_path

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python codex_file_cleaner.py <raw_json_file> <invoice_pdf_file>")
        sys.exit(1)
    process_cleaning(sys.argv[1], sys.argv[2])