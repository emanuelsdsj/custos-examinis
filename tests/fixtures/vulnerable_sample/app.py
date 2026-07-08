import sqlite3

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"


def get_user(username):
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchone()


def load_config():
    try:
        return open("config.json").read()
    except:
        pass
