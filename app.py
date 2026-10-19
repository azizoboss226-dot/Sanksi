from flask import Flask, render_template

app = Flask(__name__)
# On crée un alias pour que ZevCloud/Gunicorn le trouve
application = app 

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
