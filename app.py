from flask import Flask, render_template, request, redirect
import sqlite3
import random
import string
from datetime import datetime

app = Flask(__name__)
application = app 

# --- Initialisation de la base de données ---
def init_db():
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS demandes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference TEXT,
        montant INTEGER,
        operateur TEXT,
        id_1xbet TEXT,
        telephone TEXT,
        statut TEXT DEFAULT 'en_attente',
        created_at TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# --- Fonction pour générer une référence ---
def generer_reference():
    date_str = datetime.now().strftime("%Y%m%d")
    aleatoire = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"NC-{date_str}-{aleatoire}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/depot")
def depot():
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    reference = generer_reference()
    return render_template("depot.html", montant=montant, operateur=operateur, reference=reference)

@app.route("/depot/confirmer", methods=["POST"])
def confirmer_depot():
    montant = request.form.get("montant")
    operateur = request.form.get("operateur")
    reference = request.form.get("reference")
    id_1xbet = request.form.get("id_1xbet")
    telephone = request.form.get("telephone")
    
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("""INSERT INTO demandes (reference, montant, operateur, id_1xbet, telephone, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?)""", 
              (reference, montant, operateur, id_1xbet, telephone, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    # Page de confirmation (simple)
    return f"""
    <div style="font-family: Arial; text-align: center; padding: 50px; background: #0F172A; color: white; height: 100vh;">
        <h1 style="color: #38BDF8;">✅ Demande enregistrée !</h1>
        <p>Merci <b>{id_1xbet}</b>. Ta demande de dépôt de <b>{montant} FCFA</b> via <b>{operateur}</b> a bien été reçue.</p>
        <p>Référence : <b>{reference}</b></p>
        <p>Un agent va vérifier ton paiement et créditer ton compte très rapidement.</p>
        <a href="/" style="color: #38BDF8; margin-top: 20px; display: block;">Retour à l'accueil</a>
    </div>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
