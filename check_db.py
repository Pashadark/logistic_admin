import sqlite3


def print_schema():
    conn = sqlite3.connect('cargo_bot.db')
    c = conn.cursor()

    print("\nТаблица shipments:")
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='shipments'")
    print(c.fetchone()[0])

    print("\nТаблица users:")
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    print(c.fetchone()[0])

    conn.close()


if __name__ == "__main__":
    print_schema()