# ====== Code Summary ======
# StoreSwapper — the generation bookkeeping of an index rebuild: settle what lies under a stable name
# before copying (drop every leftover generation the live store supersedes), and swap the
# stable name onto a freshly copied, COMPLETE-stamped generation without ever leaving the collection
# with no copy of its data. Every cleanup step is written so that a failure leaves either the old
# store live (pre-swap) or the stamped new one adoptable (post-delete) — never neither.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.qdrant import QdrantAliasApi, QdrantClient

# Alias creation attempts in a swap (a transient Qdrant error must not strand the first swap).
_ALIAS_ATTEMPTS = 3
_ALIAS_BACKOFF_S = 0.5


class StoreSwapper(LoggerClass):
    """Settle leftover generations and swap a stable name onto a new one, data-loss free."""

    def __init__(self, qdrant: QdrantClient, alias_backoff_s: float = _ALIAS_BACKOFF_S) -> None:
        """
        Args:
            qdrant (QdrantClient): The vector store.
            alias_backoff_s (float): Base delay between alias attempts (linear backoff).
        """
        LoggerClass.__init__(self)
        self._qdrant = qdrant
        self._alias_backoff_s = alias_backoff_s

    async def settle(self, stable: str, old: str) -> str:
        """
        Reconcile the generations under ``stable`` before a copy; return the store to copy from.

        ``old`` is what ``stable`` resolves to — the live store every read and write already uses
        (a stranded generation was adopted by ``resolve_or_adopt`` BEFORE any lazy create, so a
        physical ``stable`` that coexists with a stamped generation can only be a store that
        survived a swap which never completed). The live store is therefore the truth and EVERY
        other generation — partial copy, superseded copy, or a stamped copy whose swap failed — is
        a leftover. Never adopted here: adopting by emptiness would resurrect deleted documents.

        Returns:
            str: ``old`` — the physical store holding the collection's data.
        """
        client = self._qdrant.raw
        for leftover in await QdrantAliasApi.generations(client, stable):
            if leftover != old:
                await self.drop_quietly(leftover)
        return old

    async def swap(self, stable: str, old: str, temp: str, *, first: bool) -> None:
        """
        Point ``stable`` at the stamped ``temp`` and drop ``old``.

        First swap (``old == stable``, physical): delete it, then create the alias — an alias cannot
        shadow a collection. ``temp`` is NEVER dropped here: a delete that raised may still complete
        server-side (client timeout), so checking ``old`` cannot prove it survived. Left stamped,
        ``temp`` is either dropped by the next ``settle`` (``old`` survived and stays the truth) or
        adopted by ``resolve_or_adopt`` (``old`` is gone) — never neither. The alias is retried.
        Later swaps: ONE atomic alias re-point; a failure there drops ``temp`` (alias still on ``old``).
        """
        client = self._qdrant.raw
        if first:
            await client.delete_collection(old)
            await self._alias_with_retry(stable, temp, replace=False)
        else:
            try:
                await self._alias_with_retry(stable, temp, replace=True)
            except BaseException:
                if await QdrantAliasApi.alias_target(client, stable) != temp:
                    await self.drop_quietly(temp)
                raise
            # A failed drop only leaves a superseded generation, cleared by the next rebuild.
            await self.drop_quietly(old)
        self.logger.info(f"Swapped '{stable}' → '{temp}' (first_rebuild={first})")

    async def _alias_with_retry(self, stable: str, temp: str, *, replace: bool) -> None:
        """Create/re-point the alias, retrying; an alias already on ``temp`` (adopted) is success."""
        client = self._qdrant.raw
        for attempt in range(1, _ALIAS_ATTEMPTS + 1):
            try:
                await QdrantAliasApi.point_alias(client, stable, temp, replace=replace)
                return
            except Exception as exc:
                if await QdrantAliasApi.alias_target(client, stable) == temp:
                    return
                if attempt == _ALIAS_ATTEMPTS:
                    raise
                self.logger.warning(f"Alias '{stable}' → '{temp}' attempt {attempt} failed: {exc}")
                await asyncio.sleep(self._alias_backoff_s * attempt)

    async def drop_quietly(self, name: str) -> None:
        """Best-effort delete of a temporary collection (a cleanup must not mask the real error)."""
        try:
            await self._qdrant.raw.delete_collection(name)
        except Exception as exc:  # cleanup only: the original failure is what gets re-raised.
            self.logger.warning(f"Could not drop temporary Qdrant collection '{name}': {exc}")


__all__ = ["StoreSwapper"]
