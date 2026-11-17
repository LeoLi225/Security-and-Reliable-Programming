"""SQLite persistence with parameterized queries, atomic checkout, and idempotency support."""
import sqlite3
from contextlib import closing
from models import Product, OrderResult


class InsufficientStockError(Exception):
    pass


class StoreRepository:
    def __init__(self, db_path='shop.db'):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=2)

    def get_product(self, sku):
        with closing(self.connect()) as conn:
            row = conn.execute(
                'SELECT sku, name, price, stock FROM products WHERE sku = ?',
                (sku,)
            ).fetchone()
            return Product(*row) if row else None

    def get_saved_cart(self, user_id):
        with closing(self.connect()) as conn:
            return conn.execute(
                'SELECT sku, quantity FROM saved_cart WHERE user_id = ?',
                (user_id,)
            ).fetchall()

    def save_cart(self, user_id, lines):
        with closing(self.connect()) as conn, conn:
            conn.execute('DELETE FROM saved_cart WHERE user_id = ?', (user_id,))
            for line in lines:
                conn.execute(
                    'INSERT INTO saved_cart (user_id, sku, quantity) VALUES (?, ?, ?)',
                    (user_id, line.sku, line.quantity)
                )

    def update_stock(self, sku, quantity):
        with closing(self.connect()) as conn, conn:
            cur = conn.execute(
                'UPDATE products SET stock = stock - ? WHERE sku = ? AND stock >= ?',
                (quantity, sku, quantity)
            )
            if cur.rowcount == 0:
                raise InsufficientStockError(f'Insufficient stock for {sku}')

    def get_order_by_request_id(self, request_id):
        if not request_id:
            return None
        with closing(self.connect()) as conn:
            row = conn.execute(
                'SELECT id, status, amount FROM orders WHERE request_id = ? ORDER BY id DESC LIMIT 1',
                (request_id,)
            ).fetchone()
            return OrderResult(row[0], row[1], row[2]) if row else None

    def finalize_paid_order(self, user_id, lines, amount, request_id):
        """Atomically deduct stock, record paid order, and clear saved cart."""
        with closing(self.connect()) as conn, conn:
            for line in lines:
                cur = conn.execute(
                    'UPDATE products SET stock = stock - ? WHERE sku = ? AND stock >= ?',
                    (line.quantity, line.sku, line.quantity)
                )
                if cur.rowcount == 0:
                    raise InsufficientStockError(f'Insufficient stock for {line.sku}')
            cur = conn.execute(
                'INSERT INTO orders(user_id, amount, status, request_id) VALUES (?, ?, ?, ?)',
                (user_id, amount, 'paid', request_id)
            )
            conn.execute('DELETE FROM saved_cart WHERE user_id = ?', (user_id,))
            return cur.lastrowid

    def save_order(self, user_id, amount, status, request_id):
        with closing(self.connect()) as conn, conn:
            cur = conn.execute(
                'INSERT INTO orders(user_id, amount, status, request_id) VALUES (?, ?, ?, ?)',
                (user_id, amount, status, request_id)
            )
            return cur.lastrowid

    def list_orders(self, user_id):
        with closing(self.connect()) as conn:
            return conn.execute(
                'SELECT id, user_id, amount, status FROM orders WHERE user_id = ? ORDER BY id DESC',
                (user_id,)
            ).fetchall()