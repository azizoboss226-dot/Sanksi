from flask import Flask, render_template, request, redirect, session
import sqlite3
import threading
import time
import random
import string
from datetime import datetime
import os
import re
import urllib.request
import urllib.parse








def init_db():
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON;")
    
    c.execute("""CREATE TABLE IF NOT EXISTS avis (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telephone TEXT, note INTEGER, commentaire TEXT, date_avis TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS demandes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, reference TEXT, montant INTEGER, operateur TEXT, 
        id_1xbet TEXT, telephone TEXT, statut TEXT DEFAULT 'en_attente', created_at TEXT, 
        message_admin TEXT, parrain TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS fidelite (
        telephone TEXT PRIMARY KEY, points INTEGER DEFAULT 0
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS historique_notifs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, date_envoi TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
        ip TEXT PRIMARY KEY, attempts INTEGER DEFAULT 0, blocked_until TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telephone TEXT, message TEXT, lu INTEGER DEFAULT 0, created_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS push_subs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telephone TEXT, endpoint TEXT UNIQUE, p256dh TEXT, auth TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS reclamations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telephone TEXT, type_op TEXT, id_op INTEGER, motif TEXT, statut TEXT DEFAULT 'en_attente', date_rec TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS retraits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code_retrait TEXT, montant INTEGER, operateur TEXT, 
        nom TEXT, telephone TEXT, statut TEXT DEFAULT 'en_attente', created_at TEXT, message_admin TEXT
    )""")
    
    conn.commit()
    conn.close()


app = Flask(__name__)
init_db()
init_db()
init_db()
app.secret_key = 'sanksi_secret_key_2026'
application = app 


import urllib.request

def envoyer_telegram_boutons(message, action_id, type_op):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Création du clavier
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Créditer", "callback_data": f"valider_{type_op}_{action_id}"},
                {"text": "❌ Refuser", "callback_data": f"refuser_{type_op}_{action_id}"}
            ]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": keyboard
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req)
    except Exception as e:
        print("Erreur Telegram Boutons:", e)

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


init_db()

def cle_tel(t):
    d = "".join(ch for ch in (t or "") if ch.isdigit())
    return d[-8:]


def pousser(telephone, message, url="/"):
    import os
import re, json
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


def get_fake_stats():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except:
        config = {}

    # Si la date de lancement n'est pas enregistrée, on l'enregistre aujourd'hui
    if 'start_date' not in config:
        config['start_date'] = datetime.now().strftime('%Y-%m-%d')
        try:
            with open('config.json', 'w') as f:
                json.dump(config, f)
        except: pass

    start_date = datetime.strptime(config['start_date'], '%Y-%m-%d')
    days_active = (datetime.now() - start_date).days

    # Si l'app a moins de 30 jours, on renvoie les faux chiffres. Sinon, 0.
    if days_active <= 30:
        return 150, 2500000
    else:
        return 0, 0

@app.route("/")
def index():
    total_clients = 0
    total_echanges = 0
    try:
        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        c.execute("""SELECT COUNT(DISTINCT t) FROM (
                        SELECT telephone AS t FROM demandes WHERE telephone IS NOT NULL AND telephone != ''
                        UNION
                        SELECT telephone AS t FROM retraits WHERE telephone IS NOT NULL AND telephone != '')""")
        total_clients = c.fetchone()[0] or 0
        c.execute("SELECT COALESCE(SUM(CAST(montant AS INTEGER)), 0) FROM demandes WHERE statut = 'valide'")
        a = c.fetchone()[0] or 0
        c.execute("SELECT COALESCE(SUM(CAST(montant AS INTEGER)), 0) FROM retraits WHERE statut = 'valide'")
        b = c.fetchone()[0] or 0
        total_echanges = a + b
        conn.close()
    except Exception as e:
        print("stats accueil erreur:", e)
    return render_template("index.html", total_clients=total_clients, total_echanges=total_echanges)

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
    if is_blacklisted(telephone):
        return "Votre numéro a été bloqué par l'administrateur. Contactez le support.", 403
    montant_check = int(request.form.get("montant", 0))
    if montant_check < 500 or montant_check > 500000:
        return "Montant invalide (Min: 500, Max: 500 000).", 400

    montant = request.form.get("montant")
    operateur = request.form.get("operateur")
    reference = request.form.get("reference")
    id_1xbet = request.form.get("id_1xbet")
    parrain = request.form.get("parrain", "")

    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("""INSERT INTO demandes (reference, montant, operateur, id_1xbet, telephone, parrain, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (reference, montant, operateur, id_1xbet, telephone, parrain, datetime.now().isoformat()))
    demande_id = c.lastrowid
    conn.commit()
    conn.close()

    msg = f"🚨 <b>NOUVEAU DÉPÔT</b>\n\n💰 Montant : <b>{montant} FCFA</b>\n📱 Opérateur : {operateur}\n🆔 ID 1xbet : <b>{id_1xbet}</b>\n📞 Téléphone : {telephone}\n🔖 Réf : {reference}\n\n👉 <a href='https://sanksi.zevcloud.app/gestion-sanksi-2026'>Valider le dépôt (Admin)</a>"
    envoyer_telegram_boutons(msg, demande_id, "depot")
    
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


@app.route("/api/reclamation", methods=["POST"])
def api_reclamation():
    data = request.get_json()
    tel = data.get("telephone")
    type_op = data.get("type_op")
    id_op = data.get("id_op")
    motif = data.get("motif")
    
    if tel and motif:
        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        c.execute("INSERT INTO reclamations (telephone, type_op, id_op, motif, date_rec) VALUES (?, ?, ?, ?, datetime('now', 'localtime'))", (tel, type_op, id_op, motif))
        conn.commit()
        conn.close()
        return {"ok": True}
    return {"ok": False}, 400

@app.route("/gestion-sanksi-2026/resoudre-rec/<int:id>")
def admin_resoudre_rec(id):
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("UPDATE reclamations SET statut = 'resolu' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/gestion-sanksi-2026")


@app.route("/api/relance-panier", methods=["POST"])
def api_relance_panier():
    data = request.get_json()
    tel = data.get("telephone")
    montant = data.get("montant")
    if tel and montant:
        envoyer_push(tel, "🛒 Tu as oublié de valider !", f"Ton dépôt de {montant} FCFA t'attend. Clique pour finir.")
        return {"ok": True}
    return {"ok": False}, 400

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
        ip = request.remote_addr or "inconnue"
        conn_sec = sqlite3.connect('sanksi.db')
        c_sec = conn_sec.cursor()
        
        # Vérifier si l'IP est bloquée
        c_sec.execute("SELECT blocked_until FROM login_attempts WHERE ip = ?", (ip,))
        row_sec = c_sec.fetchone()
        if row_sec and row_sec[0]:
            blocked_until = datetime.strptime(row_sec[0], '%Y-%m-%d %H:%M:%S')
            if datetime.now() < blocked_until:
                conn_sec.close()
                temps_restant = int((blocked_until - datetime.now()).total_seconds() / 60)
                return render_template("admin_login.html", erreur=f"Trop de tentatives. Réessayez dans {temps_restant} minutes.")
        
        password = request.form.get("password")
        if password == os.environ.get("ADMIN_PASSWORD"):
            session['admin'] = True
            c_sec.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
            conn_sec.commit()
            conn_sec.close()
            return redirect("/gestion-sanksi-2026")
        else:
            # Enregistrer l'échec
            c_sec.execute("SELECT attempts FROM login_attempts WHERE ip = ?", (ip,))
            row_att = c_sec.fetchone()
            attempts = (row_att[0] if row_att else 0) + 1
            
            if attempts >= 5:
                # Bloquer pendant 15 minutes
                blocked_until = (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
                c_sec.execute("INSERT OR REPLACE INTO login_attempts (ip, attempts, blocked_until) VALUES (?, ?, ?)", (ip, attempts, blocked_until))
                conn_sec.commit()
                conn_sec.close()
                return render_template("admin_login.html", erreur="Trop de tentatives. Compte bloqué pendant 15 minutes.")
            else:
                c_sec.execute("INSERT OR REPLACE INTO login_attempts (ip, attempts, blocked_until) VALUES (?, ?, NULL)", (ip, attempts))
                conn_sec.commit()
                conn_sec.close()
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

    # conn.close()  <-- Déplacé à la fin
    

    # --- STATISTIQUES PAR OPÉRATEUR (Aujourd'hui) ---
    conn_op = sqlite3.connect('sanksi.db')
    c_op = conn_op.cursor()
    
    c_op.execute("SELECT operateur, SUM(montant) FROM demandes WHERE statut = 'valide' AND date(created_at) = date('now', 'localtime') GROUP BY operateur")
    depots_par_op = dict(c_op.fetchall())
    
    c_op.execute("SELECT operateur, SUM(montant) FROM retraits WHERE statut = 'valide' AND date(created_at) = date('now', 'localtime') GROUP BY operateur")
    retraits_par_op = dict(c_op.fetchall())
    conn_op.close()
    
    # On prépare les variables pour le template
    total_jour_op = sum(depots_par_op.values())
    stats_orange = depots_par_op.get('Orange', 0)
    stats_moov = depots_par_op.get('Moov', 0)
    stats_wave = depots_par_op.get('Wave', 0)

    # Récupérer l'historique des notifs
    c.execute("SELECT * FROM historique_notifs ORDER BY id DESC LIMIT 5")
    historique_notifs = c.fetchall()
    
    # Récupérer les réclamations en attente
    c.execute("SELECT * FROM reclamations WHERE statut = 'en_attente' ORDER BY id DESC")
    reclamations = c.fetchall()
    total_reclamations = len(reclamations)
    
    # Calcul du Top Parrains
    c.execute("SELECT parrain, COUNT(*), SUM(montant) FROM demandes WHERE parrain IS NOT NULL AND parrain != '' AND statut = 'valide' GROUP BY parrain ORDER BY SUM(montant) DESC LIMIT 5")
    top_parrains = c.fetchall()
    
    conn.close()

    return render_template("admin_dashboard.html", historique_notifs=historique_notifs, stats_orange=stats_orange, stats_moov=stats_moov, stats_wave=stats_wave, total_jour_op=total_jour_op, reclamations=reclamations, total_reclamations=total_reclamations, 
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
        c.execute("SELECT DISTINCT telephone FROM push_subs WHERE telephone IS NOT NULL AND telephone != ''")
        telephones = c.fetchall()
        c.execute("INSERT INTO historique_notifs (message, date_envoi) VALUES (?, datetime('now', 'localtime'))", (message,))
        conn.commit()
        conn.close()
        
        for t in telephones:
            if t[0]:
                envoyer_push(t[0], "📣 Annonce SANKSI", message)
                
    return redirect("/gestion-sanksi-2026")

@app.route("/gestion-sanksi-2026/backup")
def admin_backup():
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    from flask import send_file
    import os
import re
    db_path = os.path.join(os.getcwd(), 'sanksi.db')
    return send_file(db_path, as_attachment=True, download_name="sanksi_backup.db")


@app.route("/gestion-sanksi-2026/relancer-inactifs")
def admin_relancer_inactifs():
    if not session.get('admin'): return redirect("/gestion-sanksi-2026")
    
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT ps.telephone FROM push_subs ps
        WHERE ps.telephone NOT IN (
            SELECT telephone FROM demandes
            WHERE date(created_at) >= date('now', '-7 days', 'localtime')
        )
    """)
    inactifs = c.fetchall()
    conn.close()
    
    for t in inactifs:
        if t[0]:
            envoyer_push(t[0], "🎁 Tu nous manques !", "Reviens faire un dépôt aujourd'hui sur SANKSI et gagne des points bonus !")

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
        # Nettoyage du numéro (on garde les 8 derniers chiffres)
        tel_clean = re.sub(r'\D', '', str(telephone))
        if len(tel_clean) >= 8:
            tel_clean = tel_clean[-8:]

        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        c.execute("SELECT endpoint, p256dh, auth, telephone FROM push_subs")
        all_subs = c.fetchall()
        conn.close()
        
        for sub in all_subs:
            db_tel_clean = re.sub(r'\D', '', str(sub[3]))
            if len(db_tel_clean) >= 8:
                db_tel_clean = db_tel_clean[-8:]
            
            if db_tel_clean == tel_clean:
                subscription_info = {
                    "endpoint": sub[0],
                    "keys": {"p256dh": sub[1], "auth": sub[2]}
                }
                webpush(
                    subscription_info=subscription_info,
                    data=json.dumps({"title": titre, "body": message}),
                    vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY"),
                    vapid_claims={"sub": "mailto:contact@sanksi.com"}
                )
    except Exception as e:
        print("Erreur push:", e)

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
    c.execute("SELECT COUNT(*) FROM reclamations WHERE statut = 'en_attente'")
    rec = c.fetchone()[0]
    conn.close()
    return {"d": d, "r": r, "rec": rec}


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data or "callback_query" not in data:
        return "OK", 200
        
    callback = data["callback_query"]
    callback_id = callback["id"]
    action_data = callback["data"] # ex: valider_depot_12
    
    # Répondre à Telegram pour arrêter le chargement sur le bouton
    token = os.environ.get("TELEGRAM_TOKEN")
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/answerCallbackQuery?callback_query_id={callback_id}")
    
    try:
        action, type_op, id_op = action_data.split("_")
        id_op = int(id_op)
        
        conn = sqlite3.connect('sanksi.db')
        c = conn.cursor()
        
        if type_op == "depot":
            if action == "valider":
                c.execute("UPDATE demandes SET statut = 'valide' WHERE id = ?", (id_op,))
                c.execute("SELECT telephone, montant FROM demandes WHERE id = ?", (id_op,))
                row = c.fetchone()
                if row:
                    envoyer_push(row[0], "✅ Dépôt validé !", f"Ton compte a été crédité de {row[1]} FCFA.")
            elif action == "refuser":
                c.execute("UPDATE demandes SET statut = 'refuse' WHERE id = ?", (id_op,))
                c.execute("SELECT telephone FROM demandes WHERE id = ?", (id_op,))
                row = c.fetchone()
                if row:
                    envoyer_push(row[0], "❌ Dépôt refusé", "Contacte le support pour plus d'infos.")
        
        conn.commit()
        conn.close()
        
        # Modifier le message Telegram pour montrer que c'est fait
        original_text = callback["message"]["text"]
        nouveau_texte = original_text + f"\n\n✅ <b>Traité ({action})</b>"
        edit_url = f"https://api.telegram.org/bot{token}/editMessageText"
        edit_payload = {"chat_id": callback["message"]["chat"]["id"], "message_id": callback["message"]["message_id"], "text": nouveau_texte, "parse_mode": "HTML"}
        urllib.request.urlopen(urllib.request.Request(edit_url, data=json.dumps(edit_payload).encode('utf-8'), headers={'Content-Type': 'application/json'}))
        
    except Exception as e:
        print("Erreur Webhook:", e)
        
    return "OK", 200

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
import re
    return os.environ.get("VAPID_PUBLIC_KEY", "")


@app.route("/api/push/abonner", methods=["POST"])
def push_abonner():
    from flask import jsonify
    d = request.get_json(silent=True) or {}
    tel = (d.get("telephone") or "").strip()
    sub = d.get("subscription") or {}
    keys = sub.get("keys") or {}
    if not sub.get("endpoint") or not keys.get("p256dh") or not keys.get("auth"):
        return jsonify({"ok": False}), 400
    conn = sqlite3.connect('sanksi.db')
    c = conn.cursor()
    if tel:
        c.execute("INSERT OR REPLACE INTO push_subs (telephone, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
                  (tel, sub["endpoint"], keys["p256dh"], keys["auth"]))
    else:
        c.execute("INSERT OR IGNORE INTO push_subs (telephone, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
                  ("", sub["endpoint"], keys["p256dh"], keys["auth"]))
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




import urllib.request
import mimetypes

def envoyer_document_telegram(filepath):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Tokens Telegram manquants pour la sauvegarde.")
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        
        with open(filepath, 'rb') as f:
            file_data = f.read()
            
        body = []
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="chat_id"'.encode())
        body.append(b'')
        body.append(str(chat_id).encode())
        
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="document"; filename="{filepath}"'.encode())
        body.append(b'Content-Type: application/octet-stream')
        body.append(b'')
        body.append(file_data)
        
        body.append(f'--{boundary}--'.encode())
        
        body_bytes = b'\r\n'.join(body)
        
        req = urllib.request.Request(url, data=body_bytes)
        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
        
        with urllib.request.urlopen(req) as response:
            print("✅ Sauvegarde envoyée sur Telegram")
            
    except Exception as e:
        print("Erreur envoi document:", e)

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
        # Envoyer la base de données sur Telegram
        envoyer_document_telegram('sanksi.db')
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

