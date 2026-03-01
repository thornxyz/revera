"""Supabase-backed LangGraph Store for persistent agent memory.

Replaces InMemoryStore with a Supabase Postgres table (`agent_memory`).
Uses JSONB key/namespace lookups (no pgvector) for simplicity.
"""

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    MatchCondition,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

from app.core.database import get_supabase_service_client

logger = logging.getLogger(__name__)


class SupabaseMemoryStore(BaseStore):
    """
    Persistent agent memory store backed by Supabase Postgres.

    Uses the `agent_memory` table with columns:
    - namespace (TEXT[]): Hierarchical path, e.g. ['user-id', 'chat-id', 'episodic', 'planner']
    - key (TEXT): Unique identifier within namespace
    - value (JSONB): The stored data
    - created_at, updated_at (TIMESTAMPTZ)

    All operations use the service role client (bypasses RLS).
    Semantic search (query parameter) is not supported -- falls back to namespace lookup.
    """

    TABLE = "agent_memory"

    def __init__(self):
        super().__init__()
        self._client = get_supabase_service_client(caller="SupabaseMemoryStore")

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        """Execute multiple operations synchronously."""
        results: list[Result] = []

        for op in ops:
            if isinstance(op, GetOp):
                results.append(self._handle_get(op))
            elif isinstance(op, SearchOp):
                results.append(self._handle_search(op))
            elif isinstance(op, PutOp):
                self._handle_put(op)
                results.append(None)
            elif isinstance(op, ListNamespacesOp):
                results.append(self._handle_list_namespaces(op))
            else:
                raise ValueError(f"Unsupported operation: {type(op)}")

        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        """Execute operations asynchronously (delegates to sync batch)."""
        # Supabase Python client is synchronous under the hood.
        # For true async, this would need an async Postgres driver.
        return self.batch(ops)

    def _handle_get(self, op: GetOp) -> Item | None:
        """Handle a GetOp: retrieve a single item by namespace + key."""
        namespace_list = list(op.namespace)

        try:
            result = (
                self._client.table(self.TABLE)
                .select("namespace, key, value, created_at, updated_at")
                .eq("namespace", namespace_list)
                .eq("key", str(op.key))
                .maybe_single()
                .execute()
            )

            if not result.data:
                return None

            row = result.data
            return Item(
                value=row["value"],
                key=row["key"],
                namespace=tuple(row["namespace"]),
                created_at=_parse_timestamp(row["created_at"]),
                updated_at=_parse_timestamp(row["updated_at"]),
            )
        except Exception as e:
            logger.error(f"[MEMORY_STORE] Get failed: {e}", exc_info=True)
            return None

    def _handle_search(self, op: SearchOp) -> list[SearchItem]:
        """Handle a SearchOp: search by namespace prefix.

        The `query` parameter is ignored (no pgvector / semantic search).
        Results are ordered by created_at DESC.
        """
        namespace_list = list(op.namespace_prefix)

        try:
            # Use the @> (contains) operator for prefix matching on arrays.
            # PostgREST `cs` filter = "contains" = @> operator.
            result = (
                self._client.table(self.TABLE)
                .select("namespace, key, value, created_at, updated_at")
                .contains("namespace", namespace_list)
                .order("created_at", desc=True)
                .limit(op.limit)
                .execute()
            )

            items: list[SearchItem] = []
            for row in result.data or []:
                items.append(
                    SearchItem(
                        namespace=tuple(row["namespace"]),
                        key=row["key"],
                        value=row["value"],
                        created_at=_parse_timestamp(row["created_at"]),
                        updated_at=_parse_timestamp(row["updated_at"]),
                        score=1.0,  # Exact namespace match, not scored search
                    )
                )

            return items

        except Exception as e:
            logger.error(f"[MEMORY_STORE] Search failed: {e}", exc_info=True)
            return []

    def _handle_put(self, op: PutOp) -> None:
        """Handle a PutOp: upsert or delete an item."""
        namespace_list = list(op.namespace)

        if op.value is None:
            # Delete operation
            try:
                self._client.table(self.TABLE).delete().eq(
                    "namespace", namespace_list
                ).eq("key", str(op.key)).execute()
            except Exception as e:
                logger.error(f"[MEMORY_STORE] Delete failed: {e}", exc_info=True)
            return

        # Upsert operation
        try:
            self._client.table(self.TABLE).upsert(
                {
                    "namespace": namespace_list,
                    "key": str(op.key),
                    "value": op.value,
                },
                on_conflict="namespace,key",
            ).execute()
        except Exception as e:
            logger.error(f"[MEMORY_STORE] Put failed: {e}", exc_info=True)

    def _handle_list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        """Handle a ListNamespacesOp: list distinct namespaces."""
        try:
            query = self._client.table(self.TABLE).select("namespace")

            # Apply match conditions
            for condition in op.match_conditions or ():
                if isinstance(condition, MatchCondition):
                    if condition.match_type == "prefix":
                        query = query.contains("namespace", list(condition.path))

            result = query.limit(op.limit).execute()

            # Deduplicate and optionally truncate to max_depth
            seen: set[tuple[str, ...]] = set()
            namespaces: list[tuple[str, ...]] = []

            for row in result.data or []:
                ns = tuple(row["namespace"])
                if op.max_depth is not None:
                    ns = ns[: op.max_depth]
                if ns not in seen:
                    seen.add(ns)
                    namespaces.append(ns)

            return namespaces[: op.limit]

        except Exception as e:
            logger.error(f"[MEMORY_STORE] List namespaces failed: {e}", exc_info=True)
            return []

    def delete_by_namespace_prefix(self, user_id: str, chat_id: str) -> int:
        """
        Bulk-delete all memories matching a user_id + chat_id prefix.

        Used by ChatCleanupService for cascade deletion.

        Returns:
            Number of rows deleted (approximate).
        """
        try:
            # Delete all rows where namespace contains both user_id and chat_id
            # This covers episodic (4-element) and semantic (3-element) namespaces.
            result = (
                self._client.table(self.TABLE)
                .delete()
                .contains("namespace", [user_id, chat_id])
                .execute()
            )
            deleted = len(result.data) if result.data else 0
            logger.info(
                f"[MEMORY_STORE] Bulk deleted {deleted} memories for "
                f"user={user_id}, chat={chat_id}"
            )
            return deleted
        except Exception as e:
            logger.error(f"[MEMORY_STORE] Bulk delete failed: {e}", exc_info=True)
            return 0


def _parse_timestamp(value: Any) -> datetime:
    """Parse a timestamp from Supabase (ISO string or datetime)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
