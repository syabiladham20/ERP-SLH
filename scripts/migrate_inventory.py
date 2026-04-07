import sqlite3
import os

base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'farm.db')

def migrate_inventory():
    print(f"Connecting to database at: {db_path}")
    if not os.path.exists(db_path):
        print("Database file not found!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Create inventory_item table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_item (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL, -- 'Vaccine', 'Medication'
                unit TEXT NOT NULL, -- 'Bottle', 'Kg', 'Packet', 'Liter'
                current_stock REAL DEFAULT 0,
                min_stock_level REAL DEFAULT 0,
                doses_per_unit INTEGER, -- For vaccines
                batch_number TEXT,
                expiry_date DATE,
                cost_per_unit REAL DEFAULT 0
            )
        ''')
        print("Table 'inventory_item' created or already exists.")

        # 2. Create inventory_transaction table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_transaction (
                id INTEGER PRIMARY KEY,
                inventory_item_id INTEGER NOT NULL,
                transaction_type TEXT NOT NULL, -- 'Purchase', 'Usage', 'Adjustment', 'Waste'
                quantity REAL NOT NULL,
                transaction_date DATE NOT NULL,
                notes TEXT,
                FOREIGN KEY(inventory_item_id) REFERENCES inventory_item(id)
            )
        ''')
        print("Table 'inventory_transaction' created or already exists.")

        # 3. Add columns to vaccine table
        cursor.execute("PRAGMA table_info(vaccine)")
        v_cols = [row[1] for row in cursor.fetchall()]

        if 'inventory_item_id' not in v_cols:
            print("Adding 'inventory_item_id' to 'vaccine' table...")
            cursor.execute("ALTER TABLE vaccine ADD COLUMN inventory_item_id INTEGER REFERENCES inventory_item(id)")
        else:
            print("'inventory_item_id' already exists in 'vaccine'.")

        # 4. Add columns to medication table
        cursor.execute("PRAGMA table_info(medication)")
        m_cols = [row[1] for row in cursor.fetchall()]

        if 'inventory_item_id' not in m_cols:
            print("Adding 'inventory_item_id' to 'medication' table...")
            cursor.execute("ALTER TABLE medication ADD COLUMN inventory_item_id INTEGER REFERENCES inventory_item(id)")
        else:
            print("'inventory_item_id' already exists in 'medication'.")

        if 'amount_used_qty' not in m_cols:
            print("Adding 'amount_used_qty' to 'medication' table...")
            cursor.execute("ALTER TABLE medication ADD COLUMN amount_used_qty REAL")
        else:
            print("'amount_used_qty' already exists in 'medication'.")

        conn.commit()
        print("Inventory migration successful.")

    except Exception as e:
        print(f"Error during migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_inventory()
