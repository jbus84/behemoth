from alembic.config import Config
from alembic.script import ScriptDirectory


def test_single_migration_head():
    config = Config("services/api/alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
