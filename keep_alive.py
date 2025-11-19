from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Exemple d'utilisation (si tu veux lancer le keep_alive)
# if __name__ == '__main__':
#     keep_alive()
#     # Ton code principal de bot Discord irait ici
#     # bot.run(TOKEN)
