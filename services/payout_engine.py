from decimal import Decimal
from typing import Dict, Any
from database.db import db


async def record_verified_payout(order_id: str, amount_etb: int) -> Dict[str, Any]:
    """
    Atomically transitions a PENDING order to VERIFIED and records its payout split
    into payout_ledger. Prevents double-payouts on concurrent admin button clicks.
    Sales 1-150: 60% Biruktawit / 40% Platform
    Sales 151+:  70% Biruktawit / 30% Platform
    """
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # 1. Atomic status lock: only one caller can move PENDING -> VERIFIED
            locked = await conn.fetchrow(
                """
                UPDATE orders
                SET status = 'VERIFIED', verified_at = CURRENT_TIMESTAMP
                WHERE order_id = $1 AND status = 'PENDING'
                RETURNING order_id, athlete_id, amount_etb;
                """,
                order_id
            )
            if not locked:
                return {"already_processed": True}

            # 2. Total historical completed sales count
            prior_sales = await conn.fetchval(
                "SELECT COUNT(*) FROM payout_ledger;"
            )
            current_sale_num = prior_sales + 1
            gross = Decimal(amount_etb)

            # 3. Threshold determination
            if current_sale_num <= 150:
                creator_pct = Decimal("0.60")
                platform_pct = Decimal("0.40")
                tier_label = "TIER_1_60_40"
            else:
                creator_pct = Decimal("0.70")
                platform_pct = Decimal("0.30")
                tier_label = "TIER_2_70_30"

            creator_cut = (gross * creator_pct).quantize(Decimal("0.01"))
            platform_cut = (gross * platform_pct).quantize(Decimal("0.01"))
            payout_id = f"PAY-{current_sale_num:05d}"

            # 4. Store permanent immutable record
            await conn.execute(
                """
                INSERT INTO payout_ledger (
                    payout_id, order_id, sale_number, gross_amount,
                    creator_share, platform_share, split_tier, settlement_status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'UNSETTLED')
                ON CONFLICT (order_id) DO NOTHING;
                """,
                payout_id, order_id, current_sale_num, int(gross),
                creator_cut, platform_cut, tier_label
            )

            return {
                "already_processed": False,
                "payout_id": payout_id,
                "sale_number": current_sale_num,
                "tier": tier_label,
                "gross": float(gross),
                "creator_share": float(creator_cut),
                "platform_share": float(platform_cut)
            }


async def get_creator_payout_summary() -> Dict[str, Any]:
    """
    Returns Biruktawit's earnings summary: total sales, cumulative earnings,
    unsettled payout balance, tier 1 vs tier 2 counts, and current threshold tier.
    """
    query = """
    SELECT
        COUNT(*) as total_sales,
        COALESCE(SUM(gross_amount), 0) as total_gross,
        COALESCE(SUM(creator_share), 0) as total_creator_earnings,
        COALESCE(SUM(platform_share), 0) as total_platform_earnings,
        COALESCE(SUM(CASE WHEN settlement_status = 'UNSETTLED' THEN creator_share ELSE 0 END), 0) as unsettled_creator_balance,
        COALESCE(COUNT(CASE WHEN split_tier = 'TIER_1_60_40' THEN 1 END), 0) as tier_1_count,
        COALESCE(COUNT(CASE WHEN split_tier = 'TIER_2_70_30' THEN 1 END), 0) as tier_2_count
    FROM payout_ledger;
    """
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query)
        data = dict(row)
        total_sales = data.get("total_sales", 0)
        current_tier = "TIER_1_60_40 (60% Creator)" if total_sales <= 150 else "TIER_2_70_30 (70% Creator)"
        sales_to_next_tier = max(0, 150 - total_sales)

        return {
            "total_sales": total_sales,
            "total_gross_etb": float(data.get("total_gross", 0)),
            "total_creator_earnings_etb": float(data.get("total_creator_earnings", 0)),
            "total_platform_earnings_etb": float(data.get("total_platform_earnings", 0)),
            "unsettled_creator_balance_etb": float(data.get("unsettled_creator_balance", 0)),
            "tier_1_sales_count": data.get("tier_1_count", 0),
            "tier_2_sales_count": data.get("tier_2_count", 0),
            "current_tier": current_tier,
            "sales_to_next_tier": sales_to_next_tier
        }


async def settle_unsettled_payouts() -> Dict[str, Any]:
    """
    Marks all currently unsettled creator payouts as SETTLED.
    """
    query = """
    UPDATE payout_ledger
    SET settlement_status = 'SETTLED'
    WHERE settlement_status = 'UNSETTLED'
    RETURNING payout_id, creator_share;
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
        settled_count = len(rows)
        total_settled_etb = sum(float(r["creator_share"]) for r in rows)
        return {
            "settled_count": settled_count,
            "total_settled_etb": total_settled_etb,
            "payout_ids": [r["payout_id"] for r in rows]
        }
