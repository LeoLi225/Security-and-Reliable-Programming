"""Business logic with input validation, dynamic discount calculation, and safe cart loading."""
from models import CartLine


class ShoppingCart:
    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None

    def _is_positive_int(self, value):
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    def add_item(self, sku, quantity):
        if not self._is_positive_int(quantity):
            return False
        product = self.repository.get_product(sku)
        if not product:
            return False
        existing = next((x for x in self.lines if x.sku == sku), None)
        new_qty = (existing.quantity if existing else 0) + quantity
        if product.stock < new_qty:
            return False
        if existing:
            existing.quantity = new_qty
            existing.unit_price = product.price
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        return True

    def remove_item(self, sku, quantity=None):
        if quantity is not None and not self._is_positive_int(quantity):
            return False
        for line in self.lines:
            if line.sku == sku:
                if quantity is None or quantity >= line.quantity:
                    self.lines.remove(line)
                else:
                    line.quantity -= quantity
                return True
        return False

    def subtotal(self):
        return round(sum(line.unit_price * line.quantity for line in self.lines), 2)

    def total(self):
        amount = self.subtotal()
        if not self.lines or not self.discount_code:
            return amount
        if self.discount_code == 'WELCOME10':
            amount *= 0.9
        elif self.discount_code == 'STUDENT20':
            amount *= 0.8
        elif self.discount_code == 'SAVE15':
            amount = max(0.0, amount - 15.0)
        return round(amount, 2)

    def apply_discount(self, code):
        if code not in {'WELCOME10', 'STUDENT20', 'SAVE15', 'FREESHIP'}:
            return False
        self.discount_code = code
        return True

    def load(self):
        self.lines.clear()
        self.discount_code = None
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            self.add_item(sku, quantity)

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)

        