import subprocess, pathlib
F = {"s": pathlib.Path("app/admin/service.py"), "m": pathlib.Path("app/db/models.py"), "c": pathlib.Path("app/admin/cli.py")}
orig = {k: v.read_text() for k, v in F.items()}
muts = {
 "M1 a model dropped from the count": ("s","    Agent,\n    ActionLog,\n    AdminEvent,\n)","    ActionLog,\n    AdminEvent,\n)"),
 "M2 exclusion list emptied": ("s",'STORAGE_EXCLUDED_TABLES = frozenset({"alembic_version"})',"STORAGE_EXCLUDED_TABLES = frozenset()"),
 "M3 exclusion list widened": ("s",'frozenset({"alembic_version"})','frozenset({"alembic_version", "agents"})'),
 "M4 wal not summed": ("s",'files = (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm"))','files = (path, path.with_name(path.name + "-shm"))'),
 "M5 shm not summed": ("s",', path.with_name(path.name + "-shm"))',')'),
 "M6 wrong table counted": ("s",'CHECKPOINT_TABLES = ("checkpoints", "writes")','CHECKPOINT_TABLES = ("checkpoints", "checkpoints")'),
 "M7 writes not counted": ("s",'CHECKPOINT_TABLES = ("checkpoints", "writes")','CHECKPOINT_TABLES = ("checkpoints",)'),
 "M8 size None when file exists": ("s","    return size, counts","    return None, counts"),
 "M9 overview ignores checkpoints": ("s","        checkpoint_row_counts=checkpoint_counts,\n    )","    )"),
 "M10 console omits tables": ("c","        for table, count in overview.checkpoint_row_counts.items():\n            print(f\"  {table:<20} {count}\")\n","        pass\n"),
}
def run():
    r = subprocess.run([".venv/bin/python","-m","pytest","tests/test_storage_checkpoints.py","tests/test_storage_overview.py","-q","-x","-p","no:cacheprovider"],capture_output=True,text=True)
    return r.stdout.strip().splitlines()[-1]
try:
    for name,(f,a,b) in muts.items():
        assert a in orig[f], name
        F[f].write_text(orig[f].replace(a,b,1)); print(name,"->",run()); F[f].write_text(orig[f])
    # a new table added to the schema without being counted
    F["m"].write_text(orig["m"] + '\n\nclass _Drift(Base):\n    __tablename__ = "drift_table"\n    id: Mapped[int] = mapped_column(primary_key=True)\n')
    print("M11 table added to the schema, not counted ->", run()); F["m"].write_text(orig["m"])
finally:
    for k,v in F.items(): v.write_text(orig[k])
