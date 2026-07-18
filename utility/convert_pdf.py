import os
from xhtml2pdf import pisa

source_html_path = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\esplorazione_kb_oncologico.html"
output_pdf_path = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\esplorazione_kb_oncologico.pdf"

def convert_html_to_pdf(source_html_path, output_pdf_path):
    print(f"Lettura del file HTML: {source_html_path}")
    with open(output_pdf_path, "w+b") as result_file:
        with open(source_html_path, "r", encoding="utf-8") as source_file:
            html_content = source_file.read()
            # xhtml2pdf asseconda i CSS moderni
            pisa_status = pisa.CreatePDF(
                html_content,
                dest=result_file
            )
            return pisa_status.err

if __name__ == "__main__":
    pisa.showLogging()
    err = convert_html_to_pdf(source_html_path, output_pdf_path)
    if not err:
        print("PDF generato con successo in: " + output_pdf_path)
    else:
        print(f"Errore durante la generazione del PDF: {err}")
