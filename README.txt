ECOQUILL INVOICE GENERATOR (invoice-only)

WHAT IS BUILT IN (nothing to re-enter after sleep)
- EcoQuill GSTIN 29AALFE4303K1ZA
- Canara Bank payment details
- Logo loaded from assets/business_logo.png
- TAX INVOICE title

LOGO
The EcoQuill logo is already included at assets/business_logo.png (replace the file to change it).
   (optional signature: assets/digital_signature.png)

RUN LOCALLY (PowerShell inside this folder)
  python -m pip install -r requirements.txt
  python -m streamlit run app_final.py --server.port 8507
Open http://localhost:8507

STREAMLIT CLOUD
- Replace the old files in your GitHub repo with these (keep main file: app_final.py),
  including the assets folder (logo is inside), then reboot the app.
- No Supabase / secrets needed any more. No data is stored, so nothing can be lost.
