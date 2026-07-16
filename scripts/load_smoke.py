"""Teste de carga leve e explícito para homologação do Solver.

Uso:
    python scripts/load_smoke.py --base-url https://api.solver-estatistica.com.br --requests 20 --concurrency 2

Não execute contra produção sem uma janela de homologação definida.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def payload() -> bytes:
    rows = json.loads((ROOT / "frontend/assets/data/dbc_exemplo.json").read_text(encoding="utf-8"))
    return json.dumps({
        "design": "DBC", "analysis_type": "single", "response_column": "valor",
        "treatment_column": "tratamento", "block_column": "bloco",
        "comparison_test": "tukey", "alpha_mode": "auto", "data": rows,
    }).encode("utf-8")


def one_request(url: str, body: bytes, timeout: float) -> tuple[int, float]:
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, time.perf_counter() - started


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(round((len(ordered) - 1) * fraction), len(ordered) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    url = args.base_url.rstrip("/") + "/api/analyze"
    body = payload()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(executor.map(
            lambda _: one_request(url, body, args.timeout), range(args.requests)
        ))
    statuses = [status for status, _ in results]
    durations = [duration for _, duration in results]
    report = {
        "requests": len(results), "concurrency": args.concurrency,
        "status_counts": {str(code): statuses.count(code) for code in sorted(set(statuses))},
        "latency_seconds": {
            "min": round(min(durations), 3), "mean": round(statistics.mean(durations), 3),
            "p95": round(percentile(durations, .95), 3), "max": round(max(durations), 3),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(code == 200 for code in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
