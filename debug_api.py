import os
import sys

# Add backend directory to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import FinanceDataReader as fdr
from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

print("--- ENV CHECK ---")
print(f"KIWOOM_APP_KEY: {os.getenv('KIWOOM_APP_KEY')[:5]}...")
print(f"KIWOOM_SECRET_KEY: {os.getenv('KIWOOM_SECRET_KEY')[:5]}...")

print("\n--- FDR CHECK ---")
try:
    df = fdr.StockListing("KRX")
    print(f"Columns: {df.columns.tolist()}")
    print(f"Head:\n{df[['Code', 'Name']].head() if 'Code' in df.columns else df.head()}")
    
    q = "삼성"
    name_col = next((c for c in df.columns if c.lower() == "name"), None)
    code_col = next((c for c in df.columns if c.lower() == "code"), None)
    
    if name_col and code_col:
        mask = df[name_col].str.contains(q) | df[code_col].str.contains(q)
        results = df[mask].head(5)
        print(f"\nSearch results for '{q}':\n{results[[code_col, name_col]]}")
    else:
        print("\nCould not find Name or Code columns")
except Exception as e:
    print(f"Error: {e}")

from services.kiwoom_provider import kiwoom
print("\n--- KIWOOM PROVIDER CHECK ---")
print(f"Provider App Key: {kiwoom.app_key[:5]}...")
print(f"Provider simulation: {kiwoom.is_simulation}")

# Test real price
print("\n--- REAL PRICE TEST (Samsung 005930) ---")
price = kiwoom.get_current_price("005930")
print(f"Price Result: {price}")
