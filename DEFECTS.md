# Defect Report & Test Summary

## Identified Defects & Fixes

### 1. Missing Quantity Validation & Cumulative Stock Check (`cart.py` - `ShoppingCart.add_item`)
* **Issue:** `add_item` did not validate that `quantity` is a positive integer, allowing `0`, negative numbers, or booleans/floats. Furthermore, it only checked `product.stock < quantity` for a single addition rather than cumulative cart quantity, allowing users to exceed available stock by adding the same item multiple times.
* **Fix:** Enforced strict positive integer validation (`isinstance(quantity, int) and not isinstance(quantity, bool) and quantity > 0`) and verified `(existing_quantity + quantity) <= product.stock`.

### 2. Missing Quantity Validation on Item Removal (`cart.py` - `ShoppingCart.remove_item`)
* **Issue:** Passing `0` or a negative `quantity` to `remove_item` caused `line.quantity -= quantity` to either leave the cart unchanged or inadvertently increase the item count.
* **Fix:** Validated that `quantity`, when provided, must be a positive integer; otherwise `remove_item` returns `False`.

### 3. Stale Discount Calculation, Coupon Stacking, and Negative Totals (`cart.py` - `ShoppingCart.apply_discount`, `total`)
* **Issue:** Discounts were computed once and cached in `discounted_total`. Adding or removing items afterward left the total stale. Applying coupons repeatedly compounded discounts on top of `self.total()`, and applying `SAVE15` to a subtotal under $15 produced a negative total.
* **Fix & Assumptions:** Assumed only one active discount code applies at a time (applying a new valid code replaces the previous one). Removed cached `discounted_total` and computed discounts dynamically in `total()` from the current `subtotal()`, clamping `SAVE15` at a minimum of `$0.00` and rounding monetary values to 2 decimal places.

### 4. Duplicate Accumulation on Repeated Cart Loads (`cart.py` - `ShoppingCart.load`)
* **Issue:** Calling `cart.load()` appended saved database items onto existing in-memory `cart.lines`, doubling quantities if `load()` was called multiple times.
* **Fix:** Cleared `self.lines` and reset `self.discount_code` before loading saved items from the repository.

### 5. SQL Injection Vulnerabilities (`repository.py` - `get_product`, `get_saved_cart`)
* **Issue:** User-supplied `sku` and `user_id` values were interpolated directly into SQL queries using f-strings, exposing the database to SQL injection.
* **Fix:** Replaced all string-interpolated queries with parameterized SQL statements (`?` placeholders).

### 6. Broken Access Control in Order Listing (`repository.py` - `list_orders`)
* **Issue:** `list_orders(user_id)` omitted the `WHERE user_id = ?` clause, returning orders belonging to all users.
* **Fix:** Added `WHERE user_id = ?` to isolate order history per user.

### 7. Stock Overselling at Database Layer (`repository.py` - `update_stock`)
* **Issue:** `UPDATE products SET stock = stock - ? WHERE sku = ?` allowed stock levels to drop below zero.
* **Fix:** Added `AND stock >= ?` to the `WHERE` clause and raised `InsufficientStockError` if `cur.rowcount == 0`.

### 8. Non-Atomic Checkout & Missing Rollback on Payment Failure (`checkout.py` - `CheckoutService.checkout`)
* **Issue:** Inventory was decremented before charging the payment gateway. When payment was declined or raised an exception, stock was never restored and the user's cart was still cleared.
* **Fix & Assumptions:** Assumed declined or errored payments should preserve the user's cart so they can retry. Reordered checkout to validate stock first, charge the payment gateway, and only deduct stock, record the `paid` order, and clear the saved cart inside a single atomic SQLite transaction (`finalize_paid_order`) upon payment approval.

### 9. Lack of Checkout Idempotency (`checkout.py` - `CheckoutService.checkout`, `repository.py`)
* **Issue:** Repeated checkout requests with the same `request_id` charged the customer and deducted stock multiple times.
* **Fix:** Required a non-empty `request_id` and checked `get_order_by_request_id(request_id)` prior to charging; if a `paid` order already exists for that `request_id`, the existing `OrderResult` is returned immediately without re-charging.

### 10. Real-Time Stock Re-Verification Before Charging (`checkout.py` - `CheckoutService.checkout`)
* **Issue:** Checkout did not verify current database stock before charging the payment gateway, risking charging customers for items that sold out while sitting in their cart.
* **Fix:** Added pre-payment stock verification across all cart lines, returning `OrderResult(None, 'out_of_stock', cart.total())` without charging if any item lacks sufficient stock.

### 11. Sensitive Payment Token Logged to Stdout (`checkout.py` - `CheckoutService.checkout`)
* **Issue:** `print(f'Charging payment token: {payment_token}')` exposed sensitive payment tokens in application logs.
* **Fix:** Removed the plaintext token print statement.

### 12. Database Connection Leaks on Exceptions (`repository.py`)
* **Issue:** Connections were closed manually without `try/finally` or context managers, leaking open connections if a query failed.
* **Fix:** Wrapped all SQLite connections in `contextlib.closing(...)` and transactional `with conn:` blocks.

---

## Test Execution Result

Command executed:
`python -m pytest -q`

Output:
`16 passed in 0.38s`

