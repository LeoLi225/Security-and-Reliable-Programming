"""Checkout coordinator ensuring atomicity, idempotency, stock verification, and rollback safety."""
from models import OrderResult
from repository import InsufficientStockError


class CheckoutService:
    def __init__(self, repository, payment_gateway):
        self.repository = repository
        self.payment_gateway = payment_gateway

    def checkout(self, cart, payment_token, request_id):
        if not request_id or not str(request_id).strip():
            raise ValueError('request_id is required for idempotent checkout')

        existing_order = self.repository.get_order_by_request_id(request_id)
        if existing_order and existing_order.status == 'paid':
            return existing_order

        if len(cart.lines) == 0:
            return OrderResult(None, 'empty', 0.0)

        if not payment_token or not str(payment_token).strip():
            return OrderResult(None, 'invalid_payment', cart.total())

        # Verify real-time stock before charging payment
        for line in cart.lines:
            product = self.repository.get_product(line.sku)
            if not product or product.stock < line.quantity:
                return OrderResult(None, 'out_of_stock', cart.total())

        amount = cart.total()

        try:
            response = self.payment_gateway.charge(amount, payment_token)
            approved = bool(response and response.get('approved'))
        except Exception:
            order_id = self.repository.save_order(cart.user_id, amount, 'payment_error', request_id)
            return OrderResult(order_id, 'payment_error', amount)

        if not approved:
            order_id = self.repository.save_order(cart.user_id, amount, 'declined', request_id)
            return OrderResult(order_id, 'declined', amount)

        try:
            order_id = self.repository.finalize_paid_order(
                cart.user_id, cart.lines, amount, request_id
            )
        except InsufficientStockError:
            order_id = self.repository.save_order(cart.user_id, amount, 'out_of_stock', request_id)
            return OrderResult(order_id, 'out_of_stock', amount)

        cart.lines.clear()
        cart.discount_code = None
        return OrderResult(order_id, 'paid', amount)


    