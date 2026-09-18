from fastmcp import FastMCP
import os
import aiosqlite
import tempfile
import sqlite3
import json
from typing import Optional

# ============================================================
# CONFIG
# ============================================================

TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"Database path: {DB_PATH}")

# FastMCP server instance
mcp = FastMCP("ExpenseTracker")


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")

            c.execute("""
                CREATE TABLE IF NOT EXISTS expenses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
            """)

            # Test write access
            c.execute(
                """
                INSERT OR IGNORE INTO expenses
                (date, amount, category)
                VALUES ('2000-01-01', 0, 'test')
                """
            )

            c.execute(
                "DELETE FROM expenses WHERE category = 'test'"
            )

            print("Database initialized successfully with write access")

    except Exception as e:
        print(f"Database initialization error: {e}")
        raise


init_db()


# ============================================================
# ADD EXPENSE
# ============================================================

@mcp.tool()
async def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = ""
) -> dict:
    """Add a new expense entry to the database."""

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """
                INSERT INTO expenses
                (date, amount, category, subcategory, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (date, amount, category, subcategory, note)
            )

            expense_id = cur.lastrowid

            await c.commit()

            return {
                "status": "success",
                "id": expense_id,
                "message": "Expense added successfully"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }


# ============================================================
# LIST EXPENSES
# ============================================================

@mcp.tool()
async def list_expenses(
    start_date: str,
    end_date: str
) -> list[dict]:
    """List expense entries within an inclusive date range."""

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                """,
                (start_date, end_date)
            )

            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

            return [
                dict(zip(cols, row))
                for row in rows
            ]

    except Exception as e:
        return [{
            "status": "error",
            "message": f"Error listing expenses: {str(e)}"
        }]


# ============================================================
# SUMMARIZE EXPENSES
# ============================================================

@mcp.tool()
async def summarize(
    start_date: str,
    end_date: str,
    category: Optional[str] = None
) -> list[dict]:
    """Summarize expenses by category within an inclusive date range."""

    try:
        async with aiosqlite.connect(DB_PATH) as c:

            query = """
                SELECT
                    category,
                    SUM(amount) AS total_amount,
                    COUNT(*) AS count
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """

            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += """
                GROUP BY category
                ORDER BY total_amount DESC
            """

            cur = await c.execute(query, params)

            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

            return [
                dict(zip(cols, row))
                for row in rows
            ]

    except Exception as e:
        return [{
            "status": "error",
            "message": f"Error summarizing expenses: {str(e)}"
        }]


# ============================================================
# EDIT EXPENSE
# ============================================================

@mcp.tool()
async def edit_expense(
    expense_id: int,
    date: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    note: Optional[str] = None
) -> dict:
    """Edit an existing expense. Only provided fields are changed."""

    try:
        async with aiosqlite.connect(DB_PATH) as c:

            cur = await c.execute(
                """
                SELECT date, amount, category, subcategory, note
                FROM expenses
                WHERE id = ?
                """,
                (expense_id,)
            )

            existing = await cur.fetchone()

            if existing is None:
                return {
                    "status": "error",
                    "message": f"Expense {expense_id} not found"
                }

            new_date = date if date is not None else existing[0]
            new_amount = amount if amount is not None else existing[1]
            new_category = category if category is not None else existing[2]
            new_subcategory = (
                subcategory
                if subcategory is not None
                else existing[3]
            )
            new_note = note if note is not None else existing[4]

            await c.execute(
                """
                UPDATE expenses
                SET date = ?,
                    amount = ?,
                    category = ?,
                    subcategory = ?,
                    note = ?
                WHERE id = ?
                """,
                (
                    new_date,
                    new_amount,
                    new_category,
                    new_subcategory,
                    new_note,
                    expense_id
                )
            )

            await c.commit()

            return {
                "status": "success",
                "message": f"Expense {expense_id} updated successfully"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error editing expense: {str(e)}"
        }


# ============================================================
# DELETE EXPENSE
# ============================================================

@mcp.tool()
async def delete_expense(expense_id: int) -> dict:
    """Delete an expense by its ID."""

    try:
        async with aiosqlite.connect(DB_PATH) as c:

            cur = await c.execute(
                "DELETE FROM expenses WHERE id = ?",
                (expense_id,)
            )

            await c.commit()

            if cur.rowcount == 0:
                return {
                    "status": "error",
                    "message": f"Expense {expense_id} not found"
                }

            return {
                "status": "success",
                "message": f"Expense {expense_id} deleted successfully"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error deleting expense: {str(e)}"
        }


# ============================================================
# CATEGORIES RESOURCE
# ============================================================

@mcp.resource(
    "expense:///categories",
    mime_type="application/json"
)
def categories() -> str:
    """Return available expense categories."""

    default_categories = {
        "categories": [
            "Food & Dining",
            "Transportation",
            "Shopping",
            "Entertainment",
            "Bills & Utilities",
            "Healthcare",
            "Travel",
            "Education",
            "Business",
            "Other"
        ]
    }

    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()

    except FileNotFoundError:
        return json.dumps(
            default_categories,
            indent=2
        )

    except Exception as e:
        return json.dumps({
            "error": f"Could not load categories: {str(e)}"
        })


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000
    )