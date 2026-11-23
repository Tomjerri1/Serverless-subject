import json
from pathlib import Path

out = Path("testdata")
out.mkdir(exist_ok=True)


def save(name, records):
    (out / name).write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


save("test_1.json", [{"id": "1", "name": "Alice", "updatedAt": 100},
                     {"id": "2", "name": "Bob", "updatedAt": 100}])
save("new.json", [{"id": "1", "name": "Alice New", "updatedAt": 200}])
save("old.json", [{"id": "1", "name": "Alice Old", "updatedAt": 150}])
for i in range(1, 11):
    save(f"stale_{i}.json", [{"id": "1", "name": f"Stale {i}", "updatedAt": 10}])
save("fail_1.json", [{"id": "9", "name": "Fail", "updatedAt": 1}])
print("Файли створено в", out.resolve())