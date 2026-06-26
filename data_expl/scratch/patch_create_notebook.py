import os

def main():
    target_file = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\create_notebook.py"
    tail_file = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\scratch\tail_content.txt"
    
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Cerchiamo il punto di inizio della sezione 9 (sia la vecchia che la nuova versione patchata)
    marker = '# Cell 31c:'
    idx = content.find(marker)
    if idx == -1:
        # Proviamo anche con il nome originario
        marker = '# Cell 31c: Part 9 - Audit di Copertura (Markdown)'
        idx = content.find(marker)
        
    if idx == -1:
        print("Errore: Marker '# Cell 31c:' non trovato in create_notebook.py!")
        return
        
    head = content[:idx]
    
    with open(tail_file, "r", encoding="utf-8") as f:
        tail = f.read()
        
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(head + tail)
        
    print("create_notebook.py patchato con successo unendo head e tail_content.txt!")

if __name__ == "__main__":
    main()
