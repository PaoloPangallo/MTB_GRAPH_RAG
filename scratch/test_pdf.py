import sys
from xhtml2pdf import pisa

def convert_html_to_pdf(source_html, output_filename):
    # open write and convert
    with open(output_filename, "w+b") as result_file:
        pisa_status = pisa.CreatePDF(
                source_html,                # the HTML to convert
                dest=result_file)           # file handle to receive result
    return pisa_status.err

if __name__ == "__main__":
    html = "<html><body><h1>Hello World</h1></body></html>"
    err = convert_html_to_pdf(html, "test.pdf")
    print(f"Error status: {err}")
