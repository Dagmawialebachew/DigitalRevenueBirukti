import os
import asyncpg
from typing import Optional, Dict, Any, List
from config import settings

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=5,
                max_size=25
            )
            await self.init_tables()

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

    # Athlete operations
    async def upsert_athlete(
        self,
        telegram_id: int,
        full_name: str,
        username: Optional[str] = None
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
            return dict(row)

    async def update_athlete_field(self, telegram_id: int, field: str, value: Any):
        allowed_fields = {
            "gender", "age", "weight_kg", "primary_goal",
            "days_per_week", "experience_level", "onboarding_state"
        }
        if field not in allowed_fields:
            raise ValueError(f"Invalid athlete field: {field}")
        
        query = f"""
        UPDATE athletes
        SET {field} = $1, last_interaction = CURRENT_TIMESTAMP
        WHERE telegram_id = $2;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, value, telegram_id)

    async def get_athlete(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM athletes WHERE telegram_id = $1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, telegram_id)
            return dict(row) if row else None

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
        pdf_path: str
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
        payment_method: str = "CBE"
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
        txn_ref: Optional[str] = None
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
        """
        Returns any existing completed order with the same transaction reference
        to prevent receipt replay attacks.
        """
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

    # Check-in operations (Post-purchase 8-week progress tracking)
    async def record_checkin(
        self,
        athlete_id: int,
        week_number: int,
        weight_kg: float,
        workouts_completed: int,
        notes: Optional[str] = None
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
        """
        Aggregates visitors across each funnel stage and conversion metrics.
        """
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
            "total_revenue_etb": total_revenue
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
            weight_kg = NULL,
            primary_goal = NULL,
            days_per_week = NULL,
            experience_level = NULL,
            last_interaction = CURRENT_TIMESTAMP
        WHERE telegram_id = $1;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, telegram_id)

db = Database()
