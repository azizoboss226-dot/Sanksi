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
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telephone TEXT, message TEXT,
        lu INTEGER DEFAULT 0, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS push_subs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telephone TEXT,
        endpoint TEXT UNIQUE, p256dh TEXT, auth TEXT)''')
    conn.commit()
    conn.close()

init_db()

def cle_tel(t):
    d = "".join(ch for ch in (t or "") if ch.isdigit())
    return d[-8:]


def pousser(telephone, message, url="/"):
    import os, json
    cle = os.environ.get("VAPID_PRIVATE_KEY")
    if not cle or not telephone:
        return
    try:
        from pywebpush import webpush
    except Exception:
        return
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT endpoint, p256dh, auth FROM push_subs WHERE substr(replace(replace(replace(replace(telephone,' ',''),'+',''),'-',''),'.',''), -8) = ?", (cle_tel(telephone),))
    subs = c.fetchall()
    conn.close()
    sujet = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")
    for e, p, a in subs:
        try:
            webpush(subscription_info={"endpoint": e, "keys": {"p256dh": p, "auth": a}},
                    data=json.dumps({"title": "SANKSI", "body": message, "url": url}),
                    vapid_private_key=cle, vapid_claims={"sub": sujet})
        except Exception as err:
            print("push erreur:", err)


def ajouter_notif(telephone, message):
    if not telephone:
        return
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("INSERT INTO notifications (telephone, message, lu, created_at) VALUES (?, ?, 0, ?)",
              (telephone, message, datetime.now().isoformat()))
    conn.commit()
    conn.close()

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
    c.execute("""INSERT INTO demandes (reference, montant, operateur, id_1xbet, telephone, parrain, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?)""", 
              (reference, montant, operateur, id_1xbet, telephone, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    msg = f"🚨 <b>NOUVEAU DÉPÔT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 ID 1xbet : <b>{id_1xbet}</b>\n📞 Téléphone : {telephone}\n🔖 Réf : {reference}\n\n👉 <a href='https://sanksi.zevcloud.app/gestion-sanksi-2026'>Valider le dépôt (Admin)</a>"
    envoyer_telegram(msg)

    return render_template("confirmation_depot.html", reference=reference, montant=montant)

# --- RETRAIT : ETAPE 1 (Question) ---
@app.route("/retrait/debut", methods=["GET", "POST"])
def retrait_debut():
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    
    if request.method == "POST":
        telephone = request.form.get("telephone")
        # On redirige vers l'attente avec le téléphone
        return redirect(f"/retrait/attente?montant={montant}&operateur={operateur}&telephone={telephone}")
        
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
    msg = f"🚨 <b>NOUVELLE DEMANDE DE RETRAIT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 ID Demande : {retrait_id}\n\n👉 <a href='https://sanksi.zevcloud.app/gestion-sanksi-2026'>Préparer le retrait (Admin)</a>"
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
    # On met à jour la dernière demande de retrait qui était en 'prepare'
    c.execute("""UPDATE retraits SET code_retrait = ?, nom = ?, telephone = ?, statut = 'en_attente' 
                 WHERE id = (SELECT id FROM retraits WHERE statut = 'prepare' ORDER BY id DESC LIMIT 1)""",
              (code_retrait, nom, telephone))
    conn.commit()
    conn.close()

    msg = f"🚨 <b>NOUVEAU RETRAIT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 Code retrait : <b>{code_retrait}</b>\n👤 Nom : {nom}\n📞 Téléphone : {telephone}\n\n👉 <a href='https://sanksi.zevcloud.app/gestion-sanksi-2026'>Valider le paiement (Admin)</a>"
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
    
    # 1. Récupérer les listes
    c.execute("SELECT * FROM demandes ORDER BY id DESC")
    demandes = c.fetchall()
    c.execute("SELECT * FROM retraits ORDER BY id DESC")
    retraits = c.fetchall()
    
    # 2. Calculer les statistiques
    # Total des dépôts validés
    c.execute("SELECT COUNT(*), SUM(montant) FROM demandes WHERE statut = 'valide'")
    res = c.fetchone()
    total_depots_count = res[0] or 0
    total_depots_montant = res[1] or 0
    
    # Total des retraits validés (payés)
    c.execute("SELECT COUNT(*), SUM(montant) FROM retraits WHERE statut = 'valide'")
    res = c.fetchone()
    total_retraits_count = res[0] or 0
    total_retraits_montant = res[1] or 0
    
    # Demandes en attente (dépôts)
    c.execute("SELECT COUNT(*) FROM demandes WHERE statut = 'en_attente'")
    attente_depots = c.fetchone()[0] or 0

    # Demandes en attente (retraits)
    c.execute("SELECT COUNT(*) FROM retraits WHERE statut IN ('en_attente', 'preparation', 'prepare')")
    attente_retraits = c.fetchone()[0] or 0

    conn.close()
    
    return render_template("admin_dashboard.html", 
                           demandes=demandes, 
                           retraits=retraits,
                           total_depots_count=total_depots_count,
                           total_depots_montant=total_depots_montant,
                           total_retraits_count=total_retraits_count,
                           total_retraits_montant=total_retraits_montant,
                           attente_depots=attente_depots,
                           attente_retraits=attente_retraits)



@app.route("/gestion-sanksi-2026/export-csv")
def export_csv():
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    import csv, io
    from flask import Response
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT * FROM demandes")
    demandes = c.fetchall()
    c.execute("SELECT * FROM retraits")
    retraits = c.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Type', 'ID', 'Ref/Code', 'Montant', 'Operateur', 'ID 1xBet/Nom', 'Telephone', 'Statut', 'Date'])
    for d in demandes:
        writer.writerow(['Depot', d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7]])
    for r in retraits:
        writer.writerow(['Retrait', r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]])
    
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=sanksi_export.csv"})

@app.route("/gestion-sanksi-2026/preparer/<int:id>", methods=["POST"])
def admin_preparer_retrait(id):
    if not session.get('admin'):
        return redirect("/gestion-sanksi-2026")
        
    rue = request.form.get("rue", "")
    ville = request.form.get("ville", "")
    
    # On enregistre la rue et la ville dans le champ code_retrait, séparés par un |
    infos = f"{rue}|{ville}"
    
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    
    # On récupère le téléphone du client avant de modifier
    c.execute("SELECT telephone FROM retraits WHERE id = ?", (id,))
    row = c.fetchone()
    
    c.execute("UPDATE retraits SET code_retrait = ?, statut = 'prepare' WHERE id = ?", (infos, id))

    if row and row[0]:
        c.execute("INSERT INTO notifications (telephone, message, lu, created_at) VALUES (?, ?, 0, ?)",
                  (row[0], "📍 L'agent a préparé ton retrait ! Ouvre la page d'attente pour voir la Rue et la Ville à mettre sur 1xBet.", datetime.now().isoformat()))
        pousser(row[0], "📍 L'agent a préparé ton retrait ! Ouvre la page d'attente pour voir la Rue et la Ville à mettre sur 1xBet.")
    
        
    conn.commit()
    conn.close()
    
    return redirect("/gestion-sanksi-2026")



def envoyer_push(telephone, titre, message):
    if not telephone: return
    try:
        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        c.execute("SELECT endpoint, p256dh, auth FROM push_subs WHERE telephone = ?", (telephone,))
        subs = c.fetchall()
        conn.close()
        
        for sub in subs:
            subscription_info = {
                "endpoint": sub[0],
                "keys": {"p256dh": sub[1], "auth": sub[2]}
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=json.dumps({"title": titre, "body": message}),
                    vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY"),
                    vapid_claims={"sub": "mailto:contact@sanksi.com"}
                )
            except WebPushException as ex:
                print("Erreur push:", ex)
                # Si l'abonnement est mort/expiré, on le supprime
                if ex.response and ex.response.status_code in [404, 410]:
                    conn = sqlite3.connect('sanksi.db')
                    c = conn.cursor()
                    c.execute("DELETE FROM push_subs WHERE endpoint = ?", (sub[0],))
                    conn.commit()
                    conn.close()
    except Exception as e:
        print("Erreur globale push:", e)

@app.route("/gestion-sanksi-2026/action/<type_op>/<int:id>/<action>")
def admin_action(type_op, id, action):
    if not session.get('admin'):
        return redirect("/gestion-sanksi-2026")
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    table = "demandes" if type_op == "depot" else "retraits"
    c.execute(f"SELECT montant, telephone FROM {table} WHERE id = ?", (id,))
    info = c.fetchone()
    nom_op = "dépôt" if type_op == "depot" else "retrait"
    if action == "valider":
        c.execute(f"UPDATE {table} SET statut = 'valide' WHERE id = ?", (id,))
        if info:
            c.execute("INSERT INTO notifications (telephone, message, lu, created_at) VALUES (?, ?, 0, ?)",
                      (info[1], f"✅ Ton {nom_op} de {info[0]} FCFA a été effectué.", datetime.now().isoformat()))
            pousser(info[1], f"✅ Ton {nom_op} de {info[0]} FCFA a été effectué.")
    elif action == "refuser":
        c.execute(f"UPDATE {table} SET statut = 'refuse' WHERE id = ?", (id,))
        motif = request.args.get("motif", "").strip() or "Aucun motif précisé."
        if info:
            c.execute("INSERT INTO notifications (telephone, message, lu, created_at) VALUES (?, ?, 0, ?)",
                      (info[1], f"❌ Ton {nom_op} de {info[0]} FCFA a été refusé. Motif : {motif}", datetime.now().isoformat()))
            pousser(info[1], f"❌ Ton {nom_op} de {info[0]} FCFA a été refusé. Motif : {motif}")
    conn.commit()
    conn.close()
    return redirect("/gestion-sanksi-2026")

@app.route("/api/notifications")
def api_notifications():
    from flask import jsonify
    tel = request.args.get("telephone", "").strip()
    if not tel:
        return jsonify([])
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT id, message FROM notifications WHERE substr(replace(replace(replace(replace(telephone,' ',''),'+',''),'-',''),'.',''), -8) = ? AND lu = 0 ORDER BY id", (cle_tel(tel),))
    rows = c.fetchall()
    for r in rows:
        c.execute("UPDATE notifications SET lu = 1 WHERE id = ?", (r[0],))
    conn.commit()
    conn.close()
    return jsonify([r[1] for r in rows])


@app.route("/api/push/cle")
def push_cle():
    import os
    return os.environ.get("VAPID_PUBLIC_KEY", "")


@app.route("/api/push/abonner", methods=["POST"])
def push_abonner():
    from flask import jsonify
    d = request.get_json(silent=True) or {}
    tel = (d.get("telephone") or "").strip()
    sub = d.get("subscription") or {}
    keys = sub.get("keys") or {}
    if not tel or not sub.get("endpoint") or not keys.get("p256dh") or not keys.get("auth"):
        return jsonify({"ok": False}), 400
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO push_subs (telephone, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
              (tel, sub["endpoint"], keys["p256dh"], keys["auth"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/sw.js")
def service_worker():
    from flask import send_from_directory
    rep = send_from_directory('static', 'sw.js', mimetype='application/javascript')
    rep.headers['Cache-Control'] = 'no-cache'
    return rep


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
