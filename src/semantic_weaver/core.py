from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ColumnMetadata:
    column_name: str
    definition: str
    scope: str
    measurement_basis: str
    unit: str
    aliases: list[str] = field(default_factory=list)

    def as_search_text(self) -> str:
        aliases = ", ".join(self.aliases) if self.aliases else ""
        return (
            f"column={self.column_name}; "
            f"definition={self.definition}; "
            f"scope={self.scope}; "
            f"measurement_basis={self.measurement_basis}; "
            f"unit={self.unit}; "
            f"aliases={aliases}"
        )


@dataclass
class DatabaseMetadata:
    table_name: str
    description: str
    source_system: str
    columns: list[ColumnMetadata] = field(default_factory=list)

    def as_search_text(self) -> str:
        column_text = "\n".join(c.as_search_text() for c in self.columns)
        return (
            f"table={self.table_name}; "
            f"source_system={self.source_system}; "
            f"description={self.description}\n{column_text}"
        )


@dataclass
class RetrievalHit:
    table_name: str
    column_name: str
    source_system: str
    definition: str
    scope: str
    score: float = 0.0

    @classmethod
    def from_column(cls, table: DatabaseMetadata, column: ColumnMetadata, score: float = 0.0) -> "RetrievalHit":
        return cls(
            table_name=table.table_name,
            column_name=column.column_name,
            source_system=table.source_system,
            definition=column.definition,
            scope=column.scope,
            score=score,
        )


class SemanticMetadataIndex:
    """In-memory metadata index for retrieval-grounded semantic resolution."""

    def __init__(self) -> None:
        self._dbs: list[DatabaseMetadata] = []

    def register(self, database: DatabaseMetadata) -> None:
        self._dbs.append(database)

    def _iter_columns(self) -> Iterable[tuple[DatabaseMetadata, ColumnMetadata]]:
        for database in self._dbs:
            for column in database.columns:
                yield database, column

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        if not text:
            return []

        found = re.findall(r"[A-Za-z0-9]+|[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+", text)
        tokens = [token.strip() for token in found if token and token.strip()]
        stopwords = {
            "の", "に", "は", "を", "が", "と", "も", "で", "や", "など", "及", "び", "等",
            "市", "県", "都", "府", "区", "町", "村", "年", "月", "日", "時", "分", "数"
        }
        filtered: list[str] = []
        for token in tokens:
            normalized = token.lower()
            if normalized in stopwords:
                continue
            if len(normalized) == 1 and normalized.isascii():
                continue
            filtered.append(token)
        return filtered

    def search(self, query: str) -> list[RetrievalHit]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        hits: list[RetrievalHit] = []
        for db, column in self._iter_columns():
            metadata_text = (
                db.description + " " + column.definition + " " + column.scope + " " + " ".join(column.aliases)
            ).lower()
            score = 0.0

            if any(token.lower() in metadata_text for token in query_tokens):
                score += 1.0

            if any(token.lower() in db.description.lower() for token in query_tokens):
                score += 0.6

            if any(token.lower() in column.definition.lower() for token in query_tokens):
                score += 1.2

            if any(token.lower() in column.scope.lower() for token in query_tokens):
                score += 0.7

            if any(any(token.lower() in alias.lower() for token in query_tokens) for alias in column.aliases):
                score += 1.5

            if any(token.lower() in metadata_text for token in self._tokenize(db.description + " " + column.definition + " " + column.scope)):
                score += 0.2

            if score > 0:
                hits.append(RetrievalHit.from_column(db, column, score=score))

        return sorted(hits, key=lambda hit: hit.score, reverse=True)

    def select_columns_for_query(self, query: str) -> list[RetrievalHit]:
        hits = self.search(query)
        seen: set[tuple[str, str]] = set()
        selected: list[RetrievalHit] = []
        for hit in hits:
            key = (hit.table_name, hit.column_name)
            if key in seen:
                continue
            seen.add(key)
            selected.append(hit)
        return selected


class SemanticGuardrail:
    """Checks for ambiguous or unsafe semantic merges before SQL generation."""

    def check_equivocation(self, hits: list[RetrievalHit]) -> str | None:
        if len(hits) < 2:
            return None
        definitions = {hit.definition for hit in hits}
        if len(definitions) > 1:
            defs = ", ".join(sorted(definitions))
            tables = ", ".join(sorted({hit.table_name for hit in hits}))
            return (
                "複数の定義が検出されました。実態ベースと登録ベースのどちらを指していますか？ "
                f"候補: {defs} / tables: {tables}"
            )
        return None


def generate_sql_from_metadata(hits: list[RetrievalHit], query: str) -> str:
    if not hits:
        return f"SELECT 1 WHERE false /* no metadata matched for query: {query} */"

    guardrail = SemanticGuardrail()
    clarification = guardrail.check_equivocation(hits)
    if clarification:
        # This is intentionally conservative: ask the user and do not generate a risky aggregate.
        return (
            "SELECT 1 WHERE false /* semantic guardrail: "
            f"{clarification} */"
        )

    first = hits[0]
    table = first.table_name
    column = first.column_name
    return (
        f"SELECT {table}.{column} AS selected_value "
        f"FROM {table} LIMIT 10;"
    )
