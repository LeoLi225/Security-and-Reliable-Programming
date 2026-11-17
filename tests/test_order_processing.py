"""Comprehensive unit tests covering all identified reliability and security fixes."""
import pytest
from setup_db import initialize
from repository import StoreRepository
from cart import ShoppingCart
from payments import FakePaymentGateway
from checkout import CheckoutService


@pytest.fixture
def repo(tmp_path):
    db_file = tmp_path / 'test_store.db'
    initialize(str(db_file))
    return StoreRepository(str(db_file))


def test_reject_invalid_quantities(repo):
    cart = ShoppingCart('u1', repo)
    assert not cart.add_item('MOU-01', 0)
    assert not cart.add_item('MOU-01', -3)
    assert not cart.add_item('MOU-01', 1.5)
    assert not cart.add_item('MOU-01', True)
    assert len(cart.lines) == 0


def test_cumulative_stock_check_on_repeated_adds(repo):
    cart = ShoppingCart('u1', repo)
    # LAP-01 stock is 5
    assert cart.add_item('LAP-01', 3)
    assert not cart.add_item('LAP-01', 3)
    assert cart.lines[0].quantity == 3


def test_remove_item_validation_and_partial_removal(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('USB-01', 5)
    assert not cart.remove_item('USB-01', -2)
    assert not cart.remove_item('USB-01', 0)
    assert cart.remove_item('USB-01', 2)
    assert cart.lines[0].quantity == 3
    assert cart.remove_item('USB-01', 10)
    assert len(cart.lines) == 0


def test_discount_recalculates_when_cart_modified(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 2)  # 59.90
    assert cart.apply_discount('WELCOME10')
    assert cart.total() == 53.91
    cart.add_item('USB-01', 1)  # +9.99 -> subtotal 69.89
    assert cart.total() == round(69.89 * 0.9, 2)


def test_discount_does_not_stack_and_never_negative(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('USB-01', 1)  # 9.99
    assert cart.apply_discount('STUDENT20')
    assert cart.apply_discount('SAVE15')
    assert cart.total() == 0.0
    assert not cart.apply_discount('FAKECODE')


def test_load_saved_cart_is_idempotent(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 2)
    cart.save()

    loaded_cart = ShoppingCart('u1', repo)
    loaded_cart.load()
    loaded_cart.load()  # Repeated load should not double quantity
    assert len(loaded_cart.lines) == 1
    assert loaded_cart.lines[0].quantity == 2


def test_sql_injection_prevented(repo):
    malicious_sku = "MOU-01' OR '1'='1"
    assert repo.get_product(malicious_sku) is None
    malicious_user = "u1' OR '1'='1"
    assert repo.get_saved_cart(malicious_user) == []


def test_list_orders_isolated_per_user(repo):
    repo.save_order('alice', 50.0, 'paid', 'req-a1')
    repo.save_order('bob', 80.0, 'paid', 'req-b1')
    alice_orders = repo.list_orders('alice')
    assert len(alice_orders) == 1
    assert alice_orders[0][1] == 'alice'


def test_checkout_empty_cart(repo):
    cart = ShoppingCart('u1', repo)
    gw = FakePaymentGateway(should_approve=True)
    res = CheckoutService(repo, gw).checkout(cart, 'TOK', 'req-empty')
    assert res.status == 'empty'
    assert len(gw.calls) == 0


def test_checkout_declined_preserves_stock_and_cart(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('LAP-01', 2)
    gw = FakePaymentGateway(should_approve=False)
    res = CheckoutService(repo, gw).checkout(cart, 'TOK', 'req-decline')
    assert res.status == 'declined'
    assert repo.get_product('LAP-01').stock == 5  # Unchanged
    assert len(cart.lines) == 1  # Cart preserved


def test_checkout_payment_exception_preserves_stock_and_cart(repo):
    class BrokenGateway:
        def charge(self, amount, token):
            raise RuntimeError('Gateway timeout')

    cart = ShoppingCart('u1', repo)
    cart.add_item('LAP-01', 1)
    res = CheckoutService(repo, BrokenGateway()).checkout(cart, 'TOK', 'req-err')
    assert res.status == 'payment_error'
    assert repo.get_product('LAP-01').stock == 5
    assert len(cart.lines) == 1


def test_checkout_out_of_stock_before_charging(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('LAP-01', 4)
    # Another buyer depletes stock before checkout
    repo.update_stock('LAP-01', 3)
    gw = FakePaymentGateway(should_approve=True)
    res = CheckoutService(repo, gw).checkout(cart, 'TOK', 'req-oos')
    assert res.status == 'out_of_stock'
    assert len(gw.calls) == 0  # Should not charge customer


def test_checkout_idempotency_prevents_double_charge(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 2)
    gw = FakePaymentGateway(should_approve=True)
    service = CheckoutService(repo, gw)

    first = service.checkout(cart, 'TOK', 'req-same-123')
    second = service.checkout(cart, 'TOK', 'req-same-123')

    assert first.status == 'paid'
    assert second.order_id == first.order_id
    assert len(gw.calls) == 1  # Charged only once
    assert repo.get_product('MOU-01').stock == 18  # Deducted only once


def test_checkout_requires_request_id(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 1)
    gw = FakePaymentGateway(should_approve=True)
    with pytest.raises(ValueError):
        CheckoutService(repo, gw).checkout(cart, 'TOK', '')


        