import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated
from uuid import UUID

import aio_pika
import asyncpg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://pacerly:pacerly_dev@localhost:5434/equipment",
)
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://pacerly:pacerly_dev@localhost:5672/",
)
EXCHANGE_NAME = "pacerly.events"
QUEUE_NAME = "equipment.activity_logged"
ROUTING_KEY = "activity.logged"

DEFAULT_TEST_USER = UUID("11111111-1111-1111-1111-111111111111")

db_pool: asyncpg.Pool | None = None


class ShoeCreate(BaseModel):
    brand: str = Field(..., json_schema_extra={"example": "Adidas"})
    model: str = Field(..., json_schema_extra={"example": "Supernova Rise 3"})
    nickname: str | None = Field(None, json_schema_extra={"example": "Daily Trainer"})
    max_lifespan_km: float = Field(..., gt=0, json_schema_extra={"example": 800.0})
    is_default: bool = False
    purchased_at: date | None = None


async def handle_activity_logged(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        event = json.loads(message.body.decode())
        shoe_id_raw = event.get("shoe_id")
        if not shoe_id_raw:
            return

        activity_id = UUID(event["activity_id"])
        shoe_id = UUID(shoe_id_raw)
        distance_km = float(event["total_distance_km"])

        async with db_pool.acquire() as conn, conn.transaction():
            shoe_exists = await conn.fetchval(
                "SELECT 1 FROM shoes WHERE shoe_id = $1", shoe_id
            )
            if not shoe_exists:
                return

            inserted = await conn.fetchval(
                """
                INSERT INTO shoe_mileage_logs (shoe_id, activity_id, distance_added_km)
                VALUES ($1, $2, $3)
                ON CONFLICT (activity_id) DO NOTHING
                RETURNING log_id
                """,
                shoe_id,
                activity_id,
                distance_km,
            )
            if inserted:
                await conn.execute(
                    """
                    UPDATE shoes
                    SET current_mileage_km = current_mileage_km + $1
                    WHERE shoe_id = $2
                    """,
                    distance_km,
                    shoe_id,
                )


async def consume_events() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, routing_key=ROUTING_KEY)
    await queue.consume(handle_activity_logged)

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await connection.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    consumer_task = asyncio.create_task(consume_events())
    yield
    consumer_task.cancel()
    await consumer_task
    await db_pool.close()


app = FastAPI(title="Pacerly Equipment Service", lifespan=lifespan)


def format_shoe(row: asyncpg.Record) -> dict:
    data = dict(row)
    data["max_lifespan_km"] = float(data["max_lifespan_km"])
    data["current_mileage_km"] = float(data["current_mileage_km"])
    data["wear_percentage"] = float(data["wear_percentage"])
    return data


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "equipment-service"}


@app.post("/shoes", status_code=201)
async def create_shoe(
    shoe: ShoeCreate,
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO shoes (user_id, brand, model, nickname, max_lifespan_km, is_default, purchased_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            x_user_id,
            shoe.brand,
            shoe.model,
            shoe.nickname,
            shoe.max_lifespan_km,
            shoe.is_default,
            shoe.purchased_at,
        )
    return format_shoe(row)


@app.get("/shoes")
async def list_shoes(
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM shoes WHERE user_id = $1 ORDER BY created_at DESC",
            x_user_id,
        )
    return [format_shoe(r) for r in rows]


@app.patch("/shoes/{shoe_id}/retire")
async def retire_shoe(
    shoe_id: UUID,
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE shoes
            SET status = 'retired', retired_at = NOW()
            WHERE shoe_id = $1 AND user_id = $2
            RETURNING *
            """,
            shoe_id,
            x_user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Shoe not found")
    return format_shoe(row)
