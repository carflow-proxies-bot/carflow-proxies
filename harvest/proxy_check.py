#!/usr/bin/env python3
"""Быстрая самопроверка результата proxy_harvest: свежесть файлов + выборочная живая проверка.

    python3 scripts/proxy_check.py [--sample 30] [--dir research/proxies]

Код выхода 0 — всё в порядке; 1 — списки сайтов старые (> 10 ч), почти пустые или живых в выборке < 50 %.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proxy_harvest import ALL_SITES, SITE_URL, _raise_nofile, encar_ok, pmap, site_ok, us_ok  # noqa: E402


def _check(site: str, url: str) -> bool:
    if site == "copart":
        return us_ok(url, 15) is not None
    if site == "encar":
        return encar_ok(url, 15) is not None
    return site_ok(url, SITE_URL[site], 15) is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--dir", default="research/proxies")
    a = ap.parse_args()
    _raise_nofile()
    d = Path(a.dir)
    # Проверяются списки ПО САЙТУ (site_<сайт>.txt) — их и берут воркеры бокса. Раньше проверялись
    # региональные (proxies_stable.txt: адрес пускает ВСЕ сайты региона), а они пустые: kbcha пускает
    # только корейские адреса, encar — в основном некорейские, и общих нет. Запуск был красным при
    # исправных списках (2026-10-31), и красный перестал что-либо значить.
    lists = {s: [ln.strip() for ln in (d / f"site_{s}.txt").read_text().splitlines() if ln.strip()]
             for s in ALL_SITES if (d / f"site_{s}.txt").exists()}
    if not lists:
        print("НЕТ ФАЙЛОВ site_*.txt: сборщик ещё ни разу не отработал")
        return 1
    age_h = (time.time() - max((d / f"site_{s}.txt").stat().st_mtime for s in lists)) / 3600
    all_n = sum(1 for ln in (d / "all_proxies.txt").read_text().splitlines() if ln.strip()) \
        if (d / "all_proxies.txt").exists() else 0
    print(f"обновлён {age_h:.1f} ч назад; по сайтам { {s: len(v) for s, v in lists.items()} }; всего живых {all_n}")

    # Выборка поровну по сайтам: иначе длинный список dubizzle забил бы всю выборку.
    per = max(1, a.sample // max(1, len([s for s, v in lists.items() if v])))
    sample = [(s, u) for s, v in lists.items() for u in random.sample(v, min(per, len(v)))]
    res = [x for x in pmap(lambda su: (su[0], _check(*su)), sample, len(sample) or 1, 300) if x]
    # Порог — без США: там горстка адресов за Imperva, доля живых скачет сильнее, и красный запуск из-за
    # неё прятал бы настоящие поломки Кореи и ОАЭ. США печатаем отдельно.
    main_ = [ok for s, ok in res if s != "copart"]
    us_ = [ok for s, ok in res if s == "copart"]
    by_site = {s: f"{sum(ok for x, ok in res if x == s)}/{sum(1 for x, _ in res if x == s)}" for s in lists}
    good = sum(main_)
    pct = 100 * good // len(main_) if main_ else 0
    print(f"выборка без США: {good} из {len(main_)} прямо сейчас пускают на свой сайт ({pct} %); "
          f"США: {sum(us_)} из {len(us_)}; по сайтам {by_site}")
    total = sum(len(v) for s, v in lists.items() if s != "copart")
    bad = age_h > 10 or total < 20 or pct < 50
    print("ИТОГ:", "ПРОБЛЕМА" if bad else "OK")
    return 1 if bad else 0


if __name__ == "__main__":
    import os
    rc = main()
    sys.stdout.flush()
    os._exit(rc)  # брошенные по сроку потоки не держат выход
