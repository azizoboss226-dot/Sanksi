from flask import Flask, render_template, request

app = Flask(__name__)
application = app 

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/depot")
def depot():
    # Pour l'instant, on simule les données reçues
    montant = request.args.get('montant', '0')
    operateur = request.args.get('operateur', 'Orange')
    return render_template("depot.html", montant=montant, operateur=operateur)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
