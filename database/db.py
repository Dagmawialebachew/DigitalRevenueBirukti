import asyncio
import os
import time
import asyncpg
from typing import Optional, Dict, Any, List
from config import settings


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        # Ultra-fast write-through cache for member records (avoids redundant Neon roundtrips)
        self._athlete_cache: Dict[int, tuple[float, Dict[str, Any]]] = {}
        self._cache_ttl: float = 120.0

    def _get_cached_athlete(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        entry = self._athlete_cache.get(telegram_id)
        if not entry:
            return None
        ts, data = entry
        if (time.monotonic() - ts) > self._cache_ttl:
            self._athlete_cache.pop(telegram_id, None)
            return None
        return dict(data)

    def _set_cached_athlete(self, telegram_id: int, row: Dict[str, Any]):
        if len(self._athlete_cache) > 5000:
            self._athlete_cache.clear()
        self._athlete_cache[telegram_id] = (time.monotonic(), dict(row))

    async def connect(self):
        if not self.pool:
            last_err = None
            for attempt in range(1, 4):
                try:
                    self.pool = await asyncpg.create_pool(
                        dsn=settings.DATABASE_URL,
                        min_size=2,
                        max_size=15,
                        statement_cache_size=0,  # Required for Neon PgBouncer transaction poolers
                    )
                    async with self.pool.acquire() as conn:
                        await conn.fetchval("SELECT 1;")
                    return
                except Exception as e:
                    last_err = e
                    if attempt < 3:
                        await asyncio.sleep(2)
            raise last_err

    async def init_tables(self):
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            async with self.pool.acquire() as conn:
                await conn.execute(schema_sql)

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
        self._athlete_cache.clear()

    # Athlete operations
    async def upsert_athlete(
        self,
        telegram_id: int,
        full_name: str,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = """
        INSERT INTO athletes (telegram_id, full_name, username, onboarding_state)
        VALUES ($1, $2, $3, 'START')
        ON CONFLICT (telegram_id) DO UPDATE
        SET full_name = EXCLUDED.full_name,
            username = COALESCE(EXCLUDED.username, athletes.username),
            last_interaction = CURRENT_TIMESTAMP
        RETURNING *;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, telegram_id, full_name, username)
            result = dict(row)
            self._set_cached_athlete(telegram_id, result)
            return result

    async def update_athlete_field(self, telegram_id: int, field: str, value: Any) -> Optional[Dict[str, Any]]:
        return await self.update_athlete_fields(telegram_id, **{field: value})

    async def update_athlete_fields(self, telegram_id: int, **fields: Any) -> Optional[Dict[str, Any]]:
        """Update one or more athlete columns in a single DB roundtrip and refresh cache."""
        allowed_fields = {
            "gender", "age", "age_range", "weight_kg", "primary_goal",
            "days_per_week", "experience_level", "onboarding_state",
        }
        invalid = set(fields.keys()) - allowed_fields
        if invalid:
            raise ValueError(f"Invalid athlete field(s): {invalid}")
        if not fields:
            return await self.get_athlete(telegram_id)

        assignments = []
        values = []
        idx = 1
        for col, val in fields.items():
            assignments.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1
        assignments.append("last_interaction = CURRENT_TIMESTAMP")
        values.append(telegram_id)

        query = f"""
        UPDATE athletes
        SET {', '.join(assignments)}
        WHERE telegram_id = ${idx}
        RETURNING *;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            if row:
                result = dict(row)
                self._set_cached_athlete(telegram_id, result)
                return result
            return None

    async def get_athlete(self, telegram_id: int, bypass_cache: bool = False) -> Optional[Dict[str, Any]]:
        if not bypass_cache:
            cached = self._get_cached_athlete(telegram_id)
            if cached is not None:
                return cached
        query = "SELECT * FROM athletes WHERE telegram_id = $1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, telegram_id)
            if row:
                result = dict(row)
                self._set_cached_athlete(telegram_id, result)
                return result
            return None

    # Catalog & Order operations
    async def get_catalog_product(self, gender: str, goal: str, days_per_week: int) -> Optional[Dict[str, Any]]:
        query = """
        SELECT * FROM workout_catalog
        WHERE gender = $1 AND goal = $2 AND days_per_week = $3 AND is_active = TRUE
        LIMIT 1;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, gender, goal, days_per_week)
            return dict(row) if row else None

    async def get_all_catalog_products(self) -> List[Dict[str, Any]]:
        query = "SELECT * FROM workout_catalog ORDER BY sku;"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(r) for r in rows]

    async def update_catalog_pdf_path(self, sku: str, new_pdf_path: str):
        query = "UPDATE workout_catalog SET pdf_path = $1 WHERE sku = $2;"
        async with self.pool.acquire() as conn:
            await conn.execute(query, new_pdf_path, sku)

    async def upsert_catalog_product(
        self,
        sku: str,
        title: str,
        gender: str,
        goal: str,
        days_per_week: int,
        price_etb: int,
        pdf_path: str,
    ):
        query = """
        INSERT INTO workout_catalog (sku, title, gender, goal, days_per_week, price_etb, pdf_path, is_active)
        VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
        ON CONFLICT (sku) DO UPDATE
        SET title = EXCLUDED.title,
            gender = EXCLUDED.gender,
            goal = EXCLUDED.goal,
            days_per_week = EXCLUDED.days_per_week,
            price_etb = EXCLUDED.price_etb,
            pdf_path = EXCLUDED.pdf_path;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, sku, title, gender, goal, days_per_week, price_etb, pdf_path)

    async def create_order(
        self,
        order_id: str,
        athlete_id: int,
        sku: str,
        amount_etb: int,
        payment_method: str = "CBE",
    ) -> Dict[str, Any]:
        query = """
        INSERT INTO orders (order_id, athlete_id, sku, amount_etb, payment_method, status)
        VALUES ($1, $2, $3, $4, $5, 'PENDING')
        RETURNING *;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, order_id, athlete_id, sku, amount_etb, payment_method)
            return dict(row)

    async def update_order_receipt(
        self,
        order_id: str,
        receipt_file_id: str,
        txn_ref: Optional[str] = None,
    ):
        query = """
        UPDATE orders
        SET receipt_file_id = $1,
            txn_ref = COALESCE($2, txn_ref),
            status = 'PENDING'
        WHERE order_id = $3;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, receipt_file_id, txn_ref, order_id)

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM orders WHERE order_id = $1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, order_id)
            return dict(row) if row else None

    async def get_latest_pending_order(self, athlete_id: int) -> Optional[Dict[str, Any]]:
        query = """
        SELECT * FROM orders
        WHERE athlete_id = $1 AND status = 'PENDING'
        ORDER BY created_at DESC
        LIMIT 1;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, athlete_id)
            return dict(row) if row else None

    async def check_txn_replay(self, txn_ref: str) -> Optional[Dict[str, Any]]:
        if not txn_ref:
            return None
        query = """
        SELECT * FROM orders
        WHERE txn_ref = $1 AND status IN ('VERIFIED', 'DELIVERED')
        LIMIT 1;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, txn_ref)
            return dict(row) if row else None

    async def get_recent_orders(self, limit: int = 15) -> List[Dict[str, Any]]:
        query = """
        SELECT o.*, a.full_name, a.username
        FROM orders o
        JOIN athletes a ON o.athlete_id = a.telegram_id
        ORDER BY o.created_at DESC
        LIMIT $1;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [dict(r) for r in rows]

    async def get_athlete_order_history(self, athlete_id: int) -> List[Dict[str, Any]]:
        query = """
        SELECT * FROM orders
        WHERE athlete_id = $1
        ORDER BY created_at DESC;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, athlete_id)
            return [dict(r) for r in rows]

    # Check-in operations
    async def record_checkin(
        self,
        athlete_id: int,
        week_number: int,
        weight_kg: float,
        workouts_completed: int,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = """
        INSERT INTO athlete_checkins (athlete_id, week_number, weight_kg, workouts_completed, notes)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, athlete_id, week_number, weight_kg, workouts_completed, notes)
            return dict(row)

    async def get_athlete_checkins(self, athlete_id: int) -> List[Dict[str, Any]]:
        query = """
        SELECT * FROM athlete_checkins
        WHERE athlete_id = $1
        ORDER BY week_number ASC, logged_at ASC;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, athlete_id)
            return [dict(r) for r in rows]

    async def get_latest_checkin(self, athlete_id: int) -> Optional[Dict[str, Any]]:
        query = """
        SELECT * FROM athlete_checkins
        WHERE athlete_id = $1
        ORDER BY week_number DESC, logged_at DESC
        LIMIT 1;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, athlete_id)
            return dict(row) if row else None

    # Funnel & Performance Analytics
    async def get_funnel_metrics(self) -> Dict[str, Any]:
        query_states = """
        SELECT onboarding_state, COUNT(*) as user_count
        FROM athletes
        GROUP BY onboarding_state;
        """
        query_orders = """
        SELECT status, COUNT(*) as order_count, SUM(amount_etb) as total_rev
        FROM orders
        GROUP BY status;
        """
        async with self.pool.acquire() as conn:
            state_rows = await conn.fetch(query_states)
            order_rows = await conn.fetch(query_orders)
            total_athletes = await conn.fetchval("SELECT COUNT(*) FROM athletes;")

        state_counts = {r["onboarding_state"]: r["user_count"] for r in state_rows}
        order_counts = {r["status"]: r["order_count"] for r in order_rows}
        total_revenue = sum(r["total_rev"] or 0 for r in order_rows if r["status"] in ("VERIFIED", "DELIVERED"))

        return {
            "total_athletes": total_athletes or 0,
            "state_counts": state_counts,
            "order_counts": order_counts,
            "delivered_orders": order_counts.get("DELIVERED", 0) + order_counts.get("VERIFIED", 0),
            "pending_receipts": order_counts.get("PENDING", 0),
            "total_revenue_etb": total_revenue,
        }

    async def get_admin_dashboard_stats(self) -> Dict[str, Any]:
        """Single fast roundtrip aggregating daily & lifetime metrics for /admin."""
        query = """
        SELECT
            (SELECT COUNT(*) FROM athletes) AS total_users,
            (SELECT COUNT(*) FROM athletes WHERE created_at >= CURRENT_DATE) AS today_users,
            (SELECT COUNT(*) FROM orders WHERE status IN ('VERIFIED', 'DELIVERED')) AS paid_sales,
            (SELECT COUNT(*) FROM orders WHERE status IN ('VERIFIED', 'DELIVERED') AND COALESCE(verified_at, created_at) >= CURRENT_DATE) AS today_sales,
            (SELECT COUNT(*) FROM orders WHERE status = 'PENDING' AND receipt_file_id IS NOT NULL) AS pending_receipts,
            (SELECT COUNT(*) FROM orders WHERE status = 'PENDING' AND receipt_file_id IS NULL) AS pending_checkouts,
            (SELECT COALESCE(SUM(gross_amount), 0) FROM payout_ledger) AS gross_revenue,
            (SELECT COALESCE(SUM(gross_amount), 0) FROM payout_ledger WHERE created_at >= CURRENT_DATE) AS today_revenue,
            (SELECT COALESCE(SUM(creator_share), 0) FROM payout_ledger) AS creator_earnings,
            (SELECT COALESCE(SUM(platform_share), 0) FROM payout_ledger) AS platform_earnings,
            (SELECT COALESCE(SUM(creator_share), 0) FROM payout_ledger WHERE settlement_status = 'UNSETTLED') AS unsettled_balance;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
        d = dict(row)
        return {
            "total_users": int(d.get("total_users") or 0),
            "today_users": int(d.get("today_users") or 0),
            "paid_sales": int(d.get("paid_sales") or 0),
            "today_sales": int(d.get("today_sales") or 0),
            "pending_receipts": int(d.get("pending_receipts") or 0),
            "pending_checkouts": int(d.get("pending_checkouts") or 0),
            "gross_revenue": float(d.get("gross_revenue") or 0),
            "today_revenue": float(d.get("today_revenue") or 0),
            "creator_earnings": float(d.get("creator_earnings") or 0),
            "platform_earnings": float(d.get("platform_earnings") or 0),
            "unsettled_balance": float(d.get("unsettled_balance") or 0),
        }

    async def get_recent_athletes(self, limit: int = 20) -> List[Dict[str, Any]]:
        query = """
        SELECT a.*,
               (SELECT status FROM orders o WHERE o.athlete_id = a.telegram_id ORDER BY created_at DESC LIMIT 1) as latest_order_status
        FROM athletes a
        ORDER BY a.last_interaction DESC
        LIMIT $1;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [dict(r) for r in rows]

    async def get_athlete_by_id_or_username(self, identifier: str) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            if identifier.isdigit():
                row = await conn.fetchrow("SELECT * FROM athletes WHERE telegram_id = $1;", int(identifier))
            else:
                clean_user = identifier.lstrip("@").strip()
                row = await conn.fetchrow("SELECT * FROM athletes WHERE LOWER(username) = LOWER($1);", clean_user)
            return dict(row) if row else None

    async def reset_athlete_onboarding(self, telegram_id: int):
        query = """
        UPDATE athletes
        SET onboarding_state = 'START',
            gender = NULL,
            age = NULL,
            age_range = NULL,
            weight_kg = NULL,
            primary_goal = NULL,
            days_per_week = NULL,
            experience_level = NULL,
            last_interaction = CURRENT_TIMESTAMP
        WHERE telegram_id = $1
        RETURNING *;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, telegram_id)
            if row:
                self._set_cached_athlete(telegram_id, dict(row))
            else:
                self._athlete_cache.pop(telegram_id, None)


db = Database()
