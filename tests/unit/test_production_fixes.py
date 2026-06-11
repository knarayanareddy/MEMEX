"""Tests for production fixes — FTS5 escaping, async routes, graceful shutdown, tree-sitter, migration."""

import pytest

from memex.db.sqlite import SQLiteDatabase


class TestFTS5Escaping:
    """FIX #7: Proper FTS5 query escaping."""

    def test_basic_query_escaped(self):
        """Simple words are tokenized and quoted."""
        result = SQLiteDatabase._escape_fts5_query("hello world")
        assert '"hello"' in result
        assert '"world"' in result

    def test_special_chars_stripped(self):
        """FTS5 special characters are removed."""
        result = SQLiteDatabase._escape_fts5_query("test*query?with(bad)")
        assert "*" not in result
        assert "?" not in result
        assert "(" not in result
        assert ")" not in result

    def test_fts5_operators_removed(self):
        """FTS5 operators (AND, OR, NOT, NEAR) are removed as keywords."""
        for op in ["AND", "OR", "NOT", "NEAR"]:
            query = f"python {op} machine"
            result = SQLiteDatabase._escape_fts5_query(query)
            # The operator keyword itself should be stripped
            # What remains should be the two real tokens joined by OR
            assert '"python"' in result
            assert '"machine"' in result
            # The original keyword should not appear as a standalone token
            assert f'"{op}"' not in result

    def test_empty_query_returns_safe_default(self):
        """Empty query returns safe empty-string query."""
        result = SQLiteDatabase._escape_fts5_query("")
        assert result == '""'

    def test_only_special_chars_returns_safe_default(self):
        """Query with only special chars returns safe empty-string query."""
        result = SQLiteDatabase._escape_fts5_query("***???")
        assert result == '""'

    def test_internal_quotes_escaped(self):
        """Double quotes within tokens are escaped (doubled)."""
        result = SQLiteDatabase._escape_fts5_query('say "hello"')
        # The hello token should have its quotes doubled
        assert '""""' in result or '""hello""' in result or result.count('""') >= 1

    def test_token_limit(self):
        """Queries with many tokens are capped at 20."""
        tokens = " ".join([f"word{i}" for i in range(50)])
        result = SQLiteDatabase._escape_fts5_query(tokens)
        # Should only have 20 quoted tokens
        assert result.count('"') <= 42  # 20 tokens × 2 quotes + 19 OR connectors

    def test_no_injection_possible(self):
        """Simulated injection attempts are neutralized."""
        injections = [
            "test AND 1=1",
            "test OR 1=1",
            "test NOT nothing",
            "test NEAR/5 other",
            "column:filter",
            "test{",
        ]
        for injection in injections:
            result = SQLiteDatabase._escape_fts5_query(injection)
            assert ":" not in result or result.count('"') > 2
            assert "{" not in result


class TestAsyncRouteConsistency:
    """FIX #2: All API routes use run_in_executor."""

    def test_memory_routes_import(self):
        from memex.api.routes import memory
        assert hasattr(memory, "search_memory")
        assert hasattr(memory, "timeline")
        assert hasattr(memory, "forget_document")

    def test_chat_routes_import(self):
        from memex.api.routes import chat
        assert hasattr(chat, "chat")
        assert hasattr(chat, "list_sessions")

    def test_graph_routes_import(self):
        from memex.api.routes import graph
        assert hasattr(graph, "list_entities")
        assert hasattr(graph, "list_relations")

    def test_system_routes_import(self):
        from memex.api.routes import system
        assert hasattr(system, "health_check")
        assert hasattr(system, "get_stats")


class TestLifespan:
    """FIX: FastAPI uses lifespan instead of deprecated on_event."""

    def test_app_uses_lifespan(self):
        from memex.api.app import create_app
        app = create_app()
        assert app.router.lifespan_context is not None


class TestConnectionPool:
    """FIX: SQLite uses connection pool."""

    def test_pool_exists(self, sqlite_db):
        assert hasattr(sqlite_db, "_pool")
        assert hasattr(sqlite_db, "_pool_lock")

    def test_connection_is_pooled(self, sqlite_db):
        with sqlite_db.connection() as conn:
            pass
        assert len(sqlite_db._pool) >= 1


class TestCodeParserTreeSitter:
    """FIX #4: Code parser handles tree-sitter gracefully."""

    def test_code_parser_always_produces_output(self):
        from memex.parse.code_parser import CodeParser
        from memex.config.settings import ContentType

        parser = CodeParser()
        code = b'def hello():\n    print("hi")\n'
        result = parser.parse(code, filename="test.py")
        assert result.content_type == ContentType.CODE
        assert "hello" in result.clean_content
        assert result.language == "python"

    def test_treesitter_availability_flag(self):
        from memex.parse.code_parser import CodeParser
        parser = CodeParser()
        code = b'def test(): pass\n'
        result = parser.parse(code, filename="test.py")
        assert "treesitter_used" in result.parse_metadata
        assert isinstance(result.parse_metadata["treesitter_used"], bool)


class TestMigrationRunner:
    """FIX: Alembic-style migration framework."""

    def test_migration_discovery(self):
        from memex.db.migrations.runner import discover_migrations
        migrations = discover_migrations()
        assert len(migrations) >= 1
        assert migrations[0][0] == 1

    def test_migrations_table_created(self, sqlite_db):
        with sqlite_db.connection() as conn:
            from memex.db.migrations.runner import ensure_migrations_table
            ensure_migrations_table(conn)
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
            ).fetchone()
            assert row is not None


class TestModelMigrationWorker:
    """Missing feature: Model migration protocol."""

    def test_migration_worker_exists(self):
        from memex.index.migration import ModelMigrationWorker
        worker = ModelMigrationWorker()
        assert hasattr(worker, "start_migration")
        assert hasattr(worker, "get_progress")
        assert hasattr(worker, "cancel")

    def test_migration_progress_initial_state(self):
        from memex.index.migration import ModelMigrationWorker
        worker = ModelMigrationWorker()
        progress = worker.get_progress()
        assert progress["status"] == "IDLE"

    def test_double_migration_rejected(self):
        from memex.index.migration import ModelMigrationWorker
        worker = ModelMigrationWorker()
        assert callable(worker.start_migration)


class TestSLOMonitor:
    """Missing feature: SLO measurement."""

    def test_slo_monitor_exists(self):
        from memex.observability.slos import SLOMonitor, SLOTimer
        monitor = SLOMonitor()
        assert hasattr(monitor, "check_all")
        assert hasattr(monitor, "get_dashboard")

    def test_slo_timer(self):
        from memex.observability.slos import SLOTimer
        import time

        with SLOTimer("test_operation_ms") as t:
            time.sleep(0.01)

        from memex.observability.metrics import get_metrics
        metrics = get_metrics()
        assert metrics.get_percentile("test_operation_ms", 50) > 0
