from flask import Flask, render_template, request, redirect, session
import sqlite3
import random
import string
from datetime import datetime
import os
import urllib.request
import urllib.parse

app = Flask(__name__)
app.secret_key = 'sanksi_secret_key_2026'
application = app 

def envoyer_telegram(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(url, data=data, timeout=5)
    except Exception:
        pass

def init_db():
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS demandes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, reference TEXT, montant INTEGER,
        operateur TEXT, id_1xbet TEXT, telephone TEXT,
        statut TEXT DEFAULT 'en_attente', created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS retraits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code_retrait TEXT, montant INTEGER,
        operateur TEXT, nom TEXT, telephone TEXT, statut TEXT DEFAULT 'en_attente', created_at TEXT)''')
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

# --- DEPOT ---
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

    msg = f"🚨 <b>NOUVEAU DÉPÔT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 ID 1xbet : <b>{id_1xbet}</b>\n📞 Téléphone : {telephone}\n🔖 Réf : {reference}"
    envoyer_telegram(msg)

    return render_template("confirmation_depot.html", reference=reference, montant=montant)

# --- RETRAIT : ETAPE 1 (Question) ---
@app.route("/retrait/debut")
def retrait_debut():
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    return render_template("retrait_debut.html", montant=montant, operateur=operateur)

# --- RETRAIT : ETAPE 2 (Attente des infos) ---
@app.route("/retrait/attente")
def retrait_attente():
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    
    # On crée une "demande de retrait" en attente dans la base
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("""INSERT INTO retraits (code_retrait, montant, operateur, nom, telephone, statut, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)""", 
              ("EN_ATTENTE", montant, operateur, "", "", "preparation", datetime.now().isoformat()))
    retrait_id = c.lastrowid
    conn.commit()
    conn.close()

    # 🔔 Notification Telegram pour prévenir l'admin
    msg = f"🚨 <b>NOUVELLE DEMANDE DE RETRAIT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 ID Demande : {retrait_id}\n\n👉 Va sur l'admin pour préparer les infos (Rue/Ville)."
    envoyer_telegram(msg)

    return render_template("retrait_attente.html", montant=montant, operateur=operateur, retrait_id=retrait_id)

# --- RETRAIT : ETAPE 3 (Finalisation) ---
@app.route("/retrait")
def retrait():
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    return render_template("retrait.html", montant=montant, operateur=operateur)


@app.route("/api/retrait/<int:id>")
def api_retrait(id):
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT statut, code_retrait FROM retraits WHERE id = ?", (id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"statut": "introuvable"}
    
    statut = row[0]
    info_rue = ""
    info_ville = ""
    
    # Si l'admin a mis les infos dans le champ code_retrait, on les renvoie
    if statut == 'prepare':
        infos = row[1].split('|') # On sépare rue et ville par un |
        info_rue = infos[0]
        info_ville = infos[1]
        
    return {"statut": statut, "rue": info_rue, "ville": info_ville}


@app.route("/retrait/confirmer", methods=["POST"])
def confirmer_retrait():
    montant = request.form.get("montant")
    operateur = request.form.get("operateur")
    code_retrait = request.form.get("code_retrait")
    nom = request.form.get("nom")
    telephone = request.form.get("telephone")
    
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("""INSERT INTO retraits (code_retrait, montant, operateur, nom, telephone, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?)""", 
              (code_retrait, montant, operateur, nom, telephone, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    msg = f"🚨 <b>NOUVEAU RETRAIT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 Code retrait : <b>{code_retrait}</b>\n👤 Nom : {nom}\n📞 Téléphone : {telephone}"
    envoyer_telegram(msg)

    return render_template("confirmation_retrait.html", code_retrait=code_retrait, montant=montant)

# --- HISTORIQUE ---
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

# --- ADMIN ---
@app.route("/gestion-sanksi-2026", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password")
        if password == os.environ.get("ADMIN_PASSWORD", "SanksiAdmin2026"):
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
