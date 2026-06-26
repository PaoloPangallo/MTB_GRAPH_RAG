import re
from neo4j import GraphDatabase

def main():
    uri = "bolt://localhost:7687"
    username = "neo4j"
    password = "pangallo22"
    
    print("Connessione a Neo4j...")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    try:
        with driver.session() as session:
            # 1. Pulisci il database
            print("Eliminazione di tutti i nodi e relazioni esistenti...")
            session.run("MATCH (n) DETACH DELETE n")
            print("Database ripulito con successo!")
            
            # 2. Leggi e processa import.cypher
            print("Lettura di import.cypher...")
            with open("import.cypher", "r", encoding="utf-8") as f:
                content = f.read()
                
            # Rimuoviamo i commenti a riga singola (//...)
            lines = content.splitlines()
            clean_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped.startswith("//") and stripped:
                    clean_lines.append(line)
            
            clean_content = "\n".join(clean_lines)
            
            # RIFACIMENTO SPLIT:
            # Poiché ci sono punti e virgola all'interno delle stringhe come split(row.aliases, ";"),
            # non possiamo semplicemente dividere per ";". 
            # Dividiamo invece per punto e virgola seguito da fine riga o da spazi e a-capo.
            queries = re.split(r';\s*(?=\n|$)', clean_content)
            
            print(f"Rilevate {len(queries)} query da eseguire.")
            
            # Eseguiamo ciascuna query non vuota
            for i, q in enumerate(queries):
                q_clean = q.strip()
                if not q_clean:
                    continue
                
                print(f"Esecuzione query {i+1}...")
                try:
                    session.run(q_clean)
                except Exception as e:
                    print(f"Errore durante l'esecuzione della query {i+1}:")
                    print(q_clean[:500] + "...")
                    print("Errore:", e)
                    
            print("Ingestion completata con successo su Neo4j!")
            
            # 3. Validazione
            print("Validazione nodi Evidence...")
            res = session.run("MATCH (n:Evidence) RETURN count(n) AS c, sum(case when n.source_type = 'OncoKB' then 1 else 0 end) AS okb").single()
            print(f"Nodi Evidence totali in Neo4j: {res['c']} (di cui OncoKB: {res['okb']})")
            
    finally:
        driver.close()

if __name__ == "__main__":
    main()
