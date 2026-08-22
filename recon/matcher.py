"""Deterministic + fuzzy matching engine.

Four passes, cheapest and most trustworthy first:
  1. exact reference + exact amount
  2. exact reference + amount within tolerance (fees, rounding)
  3. fuzzy reference + amount tolerance + date window (timing drift, typo'd refs)
  4. no reference at all -- amount+date is weak evidence, so this only
     matches when exactly one candidate exists on each side; anything
     ambiguous is flagged for manual review instead of guessed

Anything left over becomes an exception. A final pass looks for unmatched
pairs that share a reference but sit outside the tolerance band in a
*consistent ratio* — that's a batch-level anomaly (e.g. a currency/fee
schedule change), not N unrelated exceptions, and gets flagged separately.
"""
import difflib
from collections import Counter, defaultdict
from datetime import datetime

AMOUNT_TOLERANCE_PCT = 0.02
AMOUNT_TOLERANCE_FLOOR = 1.0
DATE_WINDOW_DAYS = 3
REF_SIMILARITY_THRESHOLD = 0.72
DRIFT_MIN_CLUSTER = 3
DRIFT_BAND_PCT = 0.005
NO_REFERENCE_CONFIDENCE = 0.5


def _within_tolerance(a, b):
    return abs(a - b) <= max(AMOUNT_TOLERANCE_FLOOR, a * AMOUNT_TOLERANCE_PCT)


def _date_diff_days(d1, d2):
    return abs((datetime.fromisoformat(d1) - datetime.fromisoformat(d2)).days)


def _has_ref(row):
    """A blank/missing reference carries zero identifying information --
    matching on it (== "") would silently cross-match unrelated
    transactions that merely happen to lack a reference number, which is a
    real, documented reconciliation failure mode, not a hypothetical one."""
    return bool(str(row.get("txn_ref", "")).strip())


def match(ledger_rows, settlement_rows):
    ledger = [dict(r, amount=float(r["amount"]), matched=False) for r in ledger_rows]
    settlement = [dict(r, amount=float(r["amount"]), matched=False) for r in settlement_rows]

    matches = []

    def unmatched(rows):
        # Sorted so ties (e.g. a duplicate settlement row that is byte-identical
        # to its original) resolve deterministically to the lowest id — which,
        # by construction, is always the original rather than a later clone.
        key = lambda r: r.get("settlement_id") or r.get("ledger_id") or ""
        return sorted((r for r in rows if not r["matched"]), key=key)

    # Pass 1: exact ref + exact amount, same day. Requires a real reference —
    # same-day is what makes this unambiguous when one exists.
    for lrow in unmatched(ledger):
        if not _has_ref(lrow):
            continue
        for srow in unmatched(settlement):
            if (
                _has_ref(srow)
                and srow["txn_ref"] == lrow["txn_ref"]
                and abs(srow["amount"] - lrow["amount"]) < 0.01
                and _date_diff_days(lrow["date"], srow["date"]) == 0
            ):
                _record(matches, lrow, srow, "exact", 1.0)
                lrow["matched"] = True
                srow["matched"] = True
                break

    # Pass 2: exact ref, amount within tolerance (fees, rounding), same day
    for lrow in unmatched(ledger):
        if not _has_ref(lrow):
            continue
        for srow in unmatched(settlement):
            if (
                _has_ref(srow)
                and srow["txn_ref"] == lrow["txn_ref"]
                and _within_tolerance(lrow["amount"], srow["amount"])
                and _date_diff_days(lrow["date"], srow["date"]) == 0
            ):
                _record(matches, lrow, srow, "fee_adjustment", 0.9)
                lrow["matched"] = True
                srow["matched"] = True
                break

    # Pass 3: fuzzy ref, amount tolerance, date window (timing drift, typo'd refs)
    for lrow in unmatched(ledger):
        if not _has_ref(lrow):
            continue
        best, best_score = None, 0.0
        for srow in unmatched(settlement):
            if not _has_ref(srow):
                continue
            if _date_diff_days(lrow["date"], srow["date"]) > DATE_WINDOW_DAYS:
                continue
            if not _within_tolerance(lrow["amount"], srow["amount"]):
                continue
            score = difflib.SequenceMatcher(None, str(lrow["txn_ref"]), str(srow["txn_ref"])).ratio()
            if score > best_score:
                best, best_score = srow, score
        if best is not None and best_score >= REF_SIMILARITY_THRESHOLD:
            label = "timing" if lrow["txn_ref"] == best["txn_ref"] else "corrupted_ref"
            _record(matches, lrow, best, label, round(best_score, 3))
            lrow["matched"] = True
            best["matched"] = True

    # Pass 4: no reference on either side. Amount+date alone is coincidental
    # evidence, not identifying evidence -- only match when there's exactly
    # one candidate on each side. Two unrelated customers who both happen to
    # pay the same amount on the same day must NOT be silently cross-matched.
    _match_unreferenced(unmatched(ledger), unmatched(settlement), matches)

    matched_refs = {m["txn_ref"] for m in matches if m["txn_ref"]}
    exceptions = _build_exceptions(unmatched(ledger), unmatched(settlement), matched_refs)
    return matches, exceptions


def _match_unreferenced(unmatched_ledger, unmatched_settlement, matches):
    def key(row):
        return (round(row["amount"], 2), row["date"])

    ledger_groups = defaultdict(list)
    for r in unmatched_ledger:
        if not _has_ref(r):
            ledger_groups[key(r)].append(r)

    settlement_groups = defaultdict(list)
    for r in unmatched_settlement:
        if not _has_ref(r):
            settlement_groups[key(r)].append(r)

    for k, lrows in ledger_groups.items():
        srows = settlement_groups.get(k, [])
        if len(lrows) == 1 and len(srows) == 1:
            lrow, srow = lrows[0], srows[0]
            _record(matches, lrow, srow, "matched_no_reference", NO_REFERENCE_CONFIDENCE)
            lrow["matched"] = True
            srow["matched"] = True


def _record(matches, lrow, srow, category, confidence):
    matches.append({
        "ledger_id": lrow["ledger_id"],
        "settlement_id": srow["settlement_id"],
        "txn_ref": lrow["txn_ref"],
        "ledger_amount": lrow["amount"],
        "settlement_amount": srow["amount"],
        "category": category,
        "confidence": confidence,
    })


def _exception_row(row, side, category):
    return {
        "ledger_id": row["ledger_id"] if side == "ledger" else "",
        "settlement_id": row["settlement_id"] if side == "settlement" else "",
        "txn_ref": row["txn_ref"],
        "amount": row["amount"],
        "date": row["date"],
        "category": category,
        "side": side,
    }


def _build_exceptions(unmatched_ledger, unmatched_settlement, matched_refs):
    referenced_settlement = [r for r in unmatched_settlement if _has_ref(r)]
    referenced_ledger = [r for r in unmatched_ledger if _has_ref(r)]
    unreferenced_settlement = [r for r in unmatched_settlement if not _has_ref(r)]
    unreferenced_ledger = [r for r in unmatched_ledger if not _has_ref(r)]

    # A leftover settlement row is a duplicate either because a second unmatched
    # copy of the same ref exists (a retried batch that never matched at all),
    # or because this ref's ledger counterpart was already satisfied by a real
    # match elsewhere (the classic case: one clean pair + one surplus payout).
    # Blank refs are excluded here -- two unrelated rows that both merely lack
    # a reference are not "duplicates of each other".
    ref_counts = Counter(r["txn_ref"] for r in referenced_settlement)
    dup_refs = {ref for ref, c in ref_counts.items() if c > 1} | (set(ref_counts) & matched_refs)

    exceptions = []
    for srow in referenced_settlement:
        category = "duplicate_settlement" if srow["txn_ref"] in dup_refs else "missing_in_ledger"
        exceptions.append(_exception_row(srow, "settlement", category))
    for lrow in referenced_ledger:
        exceptions.append(_exception_row(lrow, "ledger", "missing_in_settlement"))

    # Blank-reference rows: group by (amount, date). A group with more than
    # one candidate on either side is genuinely ambiguous -- amount+date
    # can't tell them apart, so none of them get auto-labeled "missing";
    # they're flagged for manual review instead. A lone row with no
    # counterpart at all is a real (if less certain) missing_in_*. The
    # unambiguous 1-to-1 case was already matched in pass 4 and won't
    # appear here at all.
    def key(row):
        return (round(row["amount"], 2), row["date"])

    l_groups = defaultdict(list)
    for r in unreferenced_ledger:
        l_groups[key(r)].append(r)
    s_groups = defaultdict(list)
    for r in unreferenced_settlement:
        s_groups[key(r)].append(r)

    for k, lrows in l_groups.items():
        srows = s_groups.get(k, [])
        if srows and (len(lrows) > 1 or len(srows) > 1):
            exceptions.extend(_exception_row(r, "ledger", "ambiguous_no_reference") for r in lrows)
        elif not srows:
            exceptions.extend(_exception_row(r, "ledger", "missing_in_settlement") for r in lrows)

    for k, srows in s_groups.items():
        lrows = l_groups.get(k, [])
        if lrows and (len(lrows) > 1 or len(srows) > 1):
            exceptions.extend(_exception_row(r, "settlement", "ambiguous_no_reference") for r in srows)
        elif not lrows:
            exceptions.extend(_exception_row(r, "settlement", "missing_in_ledger") for r in srows)

    _flag_batch_drift(exceptions)
    return exceptions


def _flag_batch_drift(exceptions):
    """Unmatched ledger/settlement rows that still share an exact reference
    but sit outside the tolerance band, clustered around a common ratio,
    point at one systematic cause (currency/fee-schedule change) rather
    than N unrelated exceptions."""
    by_ref = defaultdict(lambda: {"ledger": [], "settlement": []})
    for e in exceptions:
        if e["txn_ref"]:
            by_ref[e["txn_ref"]][e["side"]].append(e)

    ratios = []
    for ref, sides in by_ref.items():
        if sides["ledger"] and sides["settlement"]:
            l_amt = sides["ledger"][0]["amount"]
            s_amt = sides["settlement"][0]["amount"]
            if l_amt:
                ratios.append((ref, s_amt / l_amt))

    if len(ratios) < DRIFT_MIN_CLUSTER:
        return

    ratio_values = sorted(r for _, r in ratios)
    median = ratio_values[len(ratio_values) // 2]
    cluster_refs = {ref for ref, r in ratios if abs(r - median) <= DRIFT_BAND_PCT}

    if len(cluster_refs) >= DRIFT_MIN_CLUSTER:
        for e in exceptions:
            if e["txn_ref"] in cluster_refs and e["category"] in ("missing_in_ledger", "missing_in_settlement"):
                e["category"] = "systematic_drift_suspected"
                e["drift_ratio"] = round(median, 4)
