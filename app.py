from flask import Flask, render_template, request, redirect, session
import os
import sqlite3
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'sanksi_secret_key_2026' # Nécessaire pour la session admin
application = app 

# --- Initialisation de la base de données ---
def init_db():
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    # Table des dépôts
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
    # Table des retraits
    c.execute('''CREATE TABLE IF NOT EXISTS retraits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code_retrait TEXT,
        montant INTEGER,
        operateur TEXT,
        telephone TEXT,
        statut TEXT DEFAULT 'en_attente',
        created_at TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def generer_reference():
    date_str = datetime.now().strftime("%Y%m%d")
    aleatoire = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"NC-{date_str}-{aleatoire}"

@app.route("/")
def index():
    return render_template("index.html")

# --- ROUTES DEPOT ---
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
    return render_template("confirmation_depot.html", reference=reference, montant=montant)

# --- ROUTES RETRAIT ---
@app.route("/retrait")
def retrait():
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    return render_template("retrait.html", montant=montant, operateur=operateur)

@app.route("/retrait/confirmer", methods=["POST"])
def confirmer_retrait():
    montant = request.form.get("montant")
    operateur = request.form.get("operateur")
    code_retrait = request.form.get("code_retrait")
    telephone = request.form.get("telephone")
    
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("""INSERT INTO retraits (code_retrait, montant, operateur, telephone, created_at) 
                 VALUES (?, ?, ?, ?, ?)""", 
              (code_retrait, montant, operateur, telephone, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return render_template("confirmation_retrait.html", code_retrait=code_retrait, montant=montant)

# --- ROUTES ADMIN ---

@app.route("/historique", methods=["GET", "POST"])
def historique():
    demandes = []
    retraits = []
    tel = ""
    if request.method == "POST":
        tel = request.form.get("telephone", "").strip()
        if tel:
            conn = sqlite3.connect('sanksi.db')
            c = conn.cursor()
            c.execute("SELECT * FROM demandes WHERE telephone = ? ORDER BY id DESC", (tel,))
            demandes = c.fetchall()
            c.execute("SELECT * FROM retraits WHERE telephone = ? ORDER BY id DESC", (tel,))
            retraits = c.fetchall()
            conn.close()
    return render_template("historique.html", demandes=demandes, retraits=retraits, tel=tel)


@app.route("/gestion-sanksi-2026", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password")
        if password == os.environ.get("ADMIN_PASSWORD", "SanksiAdmin2026"): # Mot de passe admin (tu pourras le changer)
            session['admin'] = True
            return redirect("/gestion-sanksi-2026")
        else:
            return render_template("admin_login.html", erreur="Mot de passe incorrect")
            
    if not session.get('admin'):
        return render_template("admin_login.html", erreur=None)

    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT * FROM demandes ORDER BY id DESC")
    demandes = c.fetchall()
    c.execute("SELECT * FROM retraits ORDER BY id DESC")
    retraits = c.fetchall()
    conn.close()
    return render_template("admin_dashboard.html", demandes=demandes, retraits=retraits)

@app.route("/gestion-sanksi-2026/action/<type_op>/<int:id>/<action>")
def admin_action(type_op, id, action):
    if not session.get('admin'):
        return redirect("/gestion-sanksi-2026")
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    table = "demandes" if type_op == "depot" else "retraits"
    if action == "valider":
        c.execute(f"UPDATE {table} SET statut = 'valide' WHERE id = ?", (id,))
    elif action == "refuser":
        c.execute(f"UPDATE {table} SET statut = 'refuse' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/gestion-sanksi-2026")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
