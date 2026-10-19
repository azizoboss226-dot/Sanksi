from flask import Flask, render_template, request, redirect, session
import sqlite3
import threading
import time
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


import json


def is_blacklisted(telephone):
    try:
        with open('blacklist.json', 'r') as f:
            blacklist = json.load(f)
            # On nettoie le numéro pour comparer uniquement les chiffres
            tel_clean = ''.join(filter(str.isdigit, telephone))
            for b_tel in blacklist:
                if ''.join(filter(str.isdigit, b_tel)) in tel_clean:
                    return True
            return False
    except:
        return False

def check_maintenance():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            return config.get('maintenance', False)
    except:
        return False

@app.route("/")
def index():
    return render_template("index.html")

# --- DEPOT ---
@app.route("/depot")
def depot():
    if check_maintenance(): return render_template("maintenance.html")
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    id_1xbet = request.args.get('id_1xbet', '')
    reference = generer_reference()
    return render_template("depot.html", montant=montant, operateur=operateur, reference=reference, id_1xbet=id_1xbet)

@app.route("/depot/confirmer", methods=["POST"])
def confirmer_depot():
    telephone = request.form.get("telephone")
    montant_check = int(request.form.get("montant", 0))
    if montant_check < 500 or montant_check > 500000:
        return "Montant invalide (Min: 500, Max: 500 000).", 400
    if is_blacklisted(telephone):
        return "Votre numéro a été bloqué par l'administrateur. Contactez le support.", 403
    montant = request.form.get("montant")
    operateur = request.form.get("operateur")
    reference = request.form.get("reference")
    id_1xbet = request.form.get("id_1xbet")
    telephone = request.form.get("telephone")
    
    # --- ANTI-SPAM DEPOT ---
    conn_spam = sqlite3.connect('sanksi.db')
    c_spam = conn_spam.cursor()
    c_spam.execute("SELECT COUNT(*) FROM demandes WHERE telephone = ? AND statut = 'en_attente'", (telephone,))
    if c_spam.fetchone()[0] >= 2:
        conn_spam.close()
        return render_template("erreur.html", message="Tu as déjà 2 demandes de dépôt en attente. Merci de patienter ou de contacter le support.")
    conn_spam.close()
    # -----------------------
    
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("""INSERT INTO demandes (reference, montant, operateur, id_1xbet, telephone, parrain, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?)""", 
              (reference, montant, operateur, id_1xbet, telephone, datetime.now().isoformat()))
    demande_id = c.lastrowid
    conn.commit()
    conn.close()

    msg = f"🚨 <b>NOUVEAU DÉPÔT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 ID 1xbet : <b>{id_1xbet}</b>\n📞 Téléphone : {telephone}\n🔖 Réf : {reference}\n\n👉 <a href='https://sanksi.zevcloud.app/gestion-sanksi-2026'>Valider le dépôt (Admin)</a>"
    envoyer_telegram(msg)

    return render_template("confirmation_depot.html", reference=reference, montant=montant, demande_id=demande_id)

# --- RETRAIT : ETAPE 1 (Question) ---
@app.route("/retrait/debut", methods=["GET", "POST"])
def retrait_debut():
    if check_maintenance(): return render_template("maintenance.html")
    montant = request.args.get('montant', '0')
    if not montant.isdigit() or int(montant) < 500 or int(montant) > 500000:
        return "Montant invalide (Min: 500, Max: 500 000).", 400
    operateur = request.args.get('operateur', 'Orange')
    
    if request.method == "POST":
        telephone = request.form.get("telephone")
        if is_blacklisted(telephone):
            return "Votre numéro a été bloqué par l'administrateur. Contactez le support.", 403
            
        # --- ANTI-SPAM RETRAIT ---
        conn_spam = sqlite3.connect('sanksi.db')
        c_spam = conn_spam.cursor()
        c_spam.execute("SELECT COUNT(*) FROM retraits WHERE telephone = ? AND statut IN ('en_attente', 'preparation', 'prepare')", (telephone,))
        if c_spam.fetchone()[0] >= 2:
            conn_spam.close()
            return render_template("erreur.html", message="Tu as déjà 2 demandes de retrait en cours. Merci de patienter ou de contacter le support.")
        conn_spam.close()
        # -------------------------
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



@app.route("/api/depot/<int:id>")
def api_depot(id):
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT statut, message_admin FROM demandes WHERE id = ?", (id,))
    row = c.fetchone()
    conn.close()
    if not row: return {"statut": "introuvable"}
    return {"statut": row[0], "message": row[1] or ""}

@app.route("/api/retrait/<int:id>")
def api_retrait(id):
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT statut, code_retrait, message_admin FROM retraits WHERE id = ?", (id,))
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
        
    return {"statut": statut, "rue": info_rue, "ville": info_ville, "message": row[2] or ""}


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


@app.route("/api/avis", methods=["POST"])
def api_ajouter_avis():
    data = request.get_json()
    telephone = data.get("telephone")
    note = data.get("note")
    commentaire = data.get("commentaire", "")
    
    if telephone and note:
        # On anonymise le numéro (ex: 70****00)
        tel_masque = telephone[:2] + "****" + telephone[-2:] if len(telephone) > 4 else "Client"
        
        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        c.execute("INSERT INTO avis (telephone, note, commentaire, date_avis) VALUES (?, ?, ?, datetime('now', 'localtime'))", (tel_masque, note, commentaire))
        conn.commit()
        conn.close()
        return {"ok": True}
    return {"ok": False}, 400

@app.route("/api/avis/recents")
def api_avis_recents():
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT telephone, note, commentaire FROM avis ORDER BY id DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    return {"avis": [{"tel": r[0], "note": r[1], "commentaire": r[2]} for r in rows]}

@app.route("/faq")
def faq():
    return render_template("faq.html")

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
    # Récupérer les points de fidélité et le total
    points_fidelite = 0
    total_depots_valides = 0
    if tel:
        c.execute("SELECT points FROM fidelite WHERE telephone = ?", (tel,))
        row_pts = c.fetchone()
        if row_pts: points_fidelite = row_pts[0]
        conn = sqlite3.connect('sanksi.db') # on rouvre car la connexion a pu fermer dans le if
        conn.close()
        
    return render_template("historique.html", demandes=demandes, retraits=retraits, tel=tel, points=points_fidelite, total_depots=total_depots_valides)

# --- ADMIN ---
@app.route("/gestion-sanksi-2026", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password")
        if password == os.environ.get("ADMIN_PASSWORD"):
            session['admin'] = True
            return redirect("/gestion-sanksi-2026")
        else:
            return render_template("admin_login.html", erreur="Mot de passe incorrect")
            
    if not session.get('admin'):
        return render_template("admin_login.html", erreur=None)

    # --- NETTOYAGE AUTOMATIQUE ---
    conn_clean = sqlite3.connect('sanksi.db')
    c_clean = conn_clean.cursor()
    # --- NETTOYAGE AVEC NOTIFICATION PUSH ---
    # 1. Dépôts expirés
    c_clean.execute("SELECT id, telephone, montant FROM demandes WHERE statut = 'en_attente' AND created_at < datetime('now', '-30 minutes', 'localtime')")
    depots_expires = c_clean.fetchall()
    for d in depots_expires:
        c_clean.execute("UPDATE demandes SET statut = 'expire' WHERE id = ?", (d[0],))
        if d[1]:
            envoyer_push(d[1], "⏰ Dépôt expiré", f"Ta demande de {d[2]} FCFA a expiré. Merci de recommencer.")
            
    # 2. Retraits expirés
    c_clean.execute("SELECT id, telephone, montant FROM retraits WHERE statut = 'en_attente' AND created_at < datetime('now', '-1 hour', 'localtime')")
    retraits_expires = c_clean.fetchall()
    for r in retraits_expires:
        c_clean.execute("UPDATE retraits SET statut = 'expire' WHERE id = ?", (r[0],))
        if r[1]:
            envoyer_push(r[1], "⏰ Retrait expiré", f"Ta demande de {r[2]} FCFA a expiré. Merci de recommencer.")
            
    conn_clean.commit()
    conn_clean.close()
    # ---------------------------------------
    # ------------------------------

    conn = sqlite3.connect('sanksi.db')
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    
    # 1. Récupérer les listes
    c.execute("SELECT * FROM demandes ORDER BY id DESC LIMIT 100")
    demandes = c.fetchall()
    c.execute("SELECT * FROM retraits ORDER BY id DESC LIMIT 100")
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
    
    # Récupérer l'historique des notifs
    c.execute("SELECT * FROM historique_notifs ORDER BY id DESC LIMIT 5")
    historique_notifs = c.fetchall()
    
    return render_template("admin_dashboard.html", historique_notifs=historique_notifs, 
                           demandes=demandes, 
                           retraits=retraits,
                           total_depots_count=total_depots_count,
                           total_depots_montant=total_depots_montant,
                           total_retraits_count=total_retraits_count,
                           total_retraits_montant=total_retraits_montant,
                           attente_depots=attente_depots,
                           attente_retraits=attente_retraits, top_parrains=top_parrains, is_maintenance=check_maintenance())




@app.route("/gestion-sanksi-2026/toggle-maintenance")
def toggle_maintenance():
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    try:
        with open('config.json', 'r') as f: config = json.load(f)
    except: config = {}
    config['maintenance'] = not config.get('maintenance', False)
    with open('config.json', 'w') as f: json.dump(config, f)
    return redirect("/gestion-sanksi-2026")


@app.route("/gestion-sanksi-2026/bloquer/<telephone>")
def admin_bloquer(telephone):
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    try:
        with open('blacklist.json', 'r') as f: blacklist = json.load(f)
    except: blacklist = []
    
    # Si le numéro est déjà dans la liste, on le retire (débloquer)
    if telephone in blacklist:
        blacklist.remove(telephone)
    else:
        blacklist.append(telephone)
        
    with open('blacklist.json', 'w') as f: json.dump(blacklist, f)
    return redirect("/gestion-sanksi-2026")


@app.route("/gestion-sanksi-2026/push-all", methods=["POST"])
def admin_push_all():
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    message = request.form.get("message")
    if message:
        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        c.execute("SELECT telephone FROM push_subs")
        abonnes = c.fetchall()
        conn.close()
        
        for abonne in abonnes:
            envoyer_push(abonne[0], "📣 Annonce SANKSI", message)
        
        # Sauvegarder dans l'historique
        c.execute("INSERT INTO historique_notifs (message, date_envoi) VALUES (?, datetime('now', 'localtime'))", (message,))
        conn.commit()
            
    return redirect("/gestion-sanksi-2026")


@app.route("/gestion-sanksi-2026/backup")
def admin_backup():
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    from flask import send_file
    import os
    db_path = os.path.join(os.getcwd(), 'sanksi.db')
    return send_file(db_path, as_attachment=True, download_name="sanksi_backup.db")


@app.route("/gestion-sanksi-2026/relancer-inactifs")
def admin_relancer_inactifs():
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    
    # Trouver les clients qui ont un abonnement Push mais AUCUN dépôt dans les 7 derniers jours
    c.execute("""
        SELECT DISTINCT ps.telephone FROM push_subs ps
        WHERE ps.telephone NOT IN (
            SELECT telephone FROM demandes
            WHERE date(created_at) >= date('now', '-7 days', 'localtime')
        )
    """)
    inactifs = c.fetchall()
    conn.close()

    count = 0
    for t in inactifs:
        if t[0]:
            envoyer_push(t[0], "🎁 Tu nous manques !", "Reviens faire un dépôt aujourd'hui sur SANKSI et gagne des points bonus !")
            count += 1

    return redirect("/gestion-sanksi-2026")

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


@app.route("/gestion-sanksi-2026/message/<type_op>/<int:id>", methods=["POST"])
def admin_message(type_op, id):
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    message = request.form.get("message")
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    if type_op == 'depot':
        c.execute("UPDATE demandes SET message_admin = ? WHERE id = ?", (message, id))
        c.execute("SELECT telephone FROM demandes WHERE id = ?", (id,))
    else:
        c.execute("UPDATE retraits SET message_admin = ? WHERE id = ?", (message, id))
        c.execute("SELECT telephone FROM retraits WHERE id = ?", (id,))
    tel = c.fetchone()
    conn.commit()
    conn.close()
    
    # On envoie aussi une notification Push
    if tel and tel[0] and message:
        envoyer_push(tel[0], "📩 Message de l'agent", message)
        
    return redirect("/gestion-sanksi-2026")

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


@app.route("/api/admin/live-check")
def api_admin_live_check():
    if not session.get('admin'): return {"d": 0, "r": 0}
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM demandes WHERE statut = 'en_attente'")
    d = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM retraits WHERE statut IN ('en_attente', 'preparation', 'prepare')")
    r = c.fetchone()[0]
    conn.close()
    return {"d": d, "r": r}

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


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500



def envoyer_rapport_quotidien():
    try:
        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*), SUM(montant) FROM demandes WHERE statut = 'valide' AND date(created_at) = date('now', 'localtime')")
        res_d = c.fetchone()
        c.execute("SELECT COUNT(*), SUM(montant) FROM retraits WHERE statut = 'valide' AND date(created_at) = date('now', 'localtime')")
        res_r = c.fetchone()
        conn.close()

        nb_d = res_d[0] or 0
        mt_d = res_d[1] or 0
        nb_r = res_r[0] or 0
        mt_r = res_r[1] or 0
        benefice = mt_d - mt_r

        msg = f"📊 <b>BILAN DU JOUR</b>\n\n"
        msg += f"🟢 Dépôts validés : <b>{nb_d}</b> ({mt_d} FCFA)\n"
        msg += f"🔴 Retraits payés : <b>{nb_r}</b> ({mt_r} FCFA)\n"
        msg += f"💼 Bénéfice net : <b>{benefice} FCFA</b>\n\n"
        msg += "Bonne nuit ! 🌙"

        envoyer_telegram(msg)
    except Exception as e:
        print("Erreur rapport:", e)

def boucle_rapport():
    while True:
        maintenant = datetime.now()
        if maintenant.hour == 23 and maintenant.minute == 59:
            envoyer_rapport_quotidien()
            time.sleep(60) # Éviter d'envoyer plusieurs fois dans la même minute
        time.sleep(30)

# Lancer le thread au démarrage de l'app
thread_rapport = threading.Thread(target=boucle_rapport)
thread_rapport.daemon = True
thread_rapport.start()

