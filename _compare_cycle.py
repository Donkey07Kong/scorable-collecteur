"""Compare user's bet261 results (J1-J11 current cycle) with our C5 predictions."""
import json

USER = {
    1: [
        ("Algeria", "Morocco", 3, 2),
        ("Mali", "Angola", 0, 0),
        ("Botswana", "Mozambique", 2, 0),
        ("Equatorial Guinea", "Uganda", 1, 0),
        ("Egypt", "Nigeria", 1, 0),
        ("DR Congo", "Tunisia", 0, 1),
        ("Ivory Coast", "Sudan", 3, 0),
        ("Zimbabwe", "Benin", 3, 0),
        ("Tanzania", "Zambia", 0, 0),
        ("Burkina Faso", "Comoros", 0, 0),
        ("South Africa", "Gabon", 4, 0),
        ("Senegal", "Cameroon", 2, 0),
    ],
    2: [
        ("Comoros", "Botswana", 0, 0),
        ("Uganda", "South Africa", 1, 2),
        ("Benin", "Burkina Faso", 1, 0),
        ("Sudan", "Cameroon", 0, 0),
        ("Nigeria", "DR Congo", 0, 0),
        ("Morocco", "Mali", 1, 1),
        ("Angola", "Ivory Coast", 0, 0),
        ("Mozambique", "Tanzania", 1, 1),
        ("Zimbabwe", "Egypt", 0, 1),
        ("Gabon", "Senegal", 0, 3),
        ("Tunisia", "Algeria", 2, 0),
        ("Zambia", "Equatorial Guinea", 2, 0),
    ],
    3: [
        ("Ivory Coast", "Morocco", 3, 1),
        ("Tanzania", "Comoros", 2, 0),
        ("Cameroon", "Angola", 1, 0),
        ("DR Congo", "Zimbabwe", 1, 0),
        ("Mali", "Tunisia", 0, 0),
        ("Equatorial Guinea", "Mozambique", 0, 0),
        ("Burkina Faso", "Egypt", 2, 1),
        ("Botswana", "Benin", 0, 0),
        ("Algeria", "Nigeria", 0, 0),
        ("Senegal", "Sudan", 3, 1),
        ("Gabon", "Uganda", 1, 2),
        ("South Africa", "Zambia", 0, 1),
    ],
    4: [
        ("Burkina Faso", "DR Congo", 2, 0),
        ("Benin", "Tanzania", 0, 3),
        ("Mozambique", "South Africa", 0, 0),
        ("Ivory Coast", "Tunisia", 1, 0),
        ("Senegal", "Uganda", 1, 0),
        ("Equatorial Guinea", "Comoros", 0, 0),
        ("Gabon", "Zambia", 0, 0),
        ("Angola", "Sudan", 3, 1),
        ("Morocco", "Cameroon", 2, 1),
        ("Zimbabwe", "Egypt", 1, 1),
        ("Algeria", "Botswana", 3, 0),
        ("Nigeria", "Mali", 0, 1),
    ],
    5: [
        ("Uganda", "Zambia", 2, 0),
        ("Sudan", "Morocco", 1, 4),
        ("Algeria", "Burkina Faso", 3, 0),
        ("South Africa", "Comoros", 2, 0),
        ("Tanzania", "Egypt", 0, 1),
        ("Gabon", "Mozambique", 0, 3),
        ("Botswana", "DR Congo", 0, 0),
        ("Equatorial Guinea", "Benin", 3, 0),
        ("Mali", "Zimbabwe", 3, 0),
        ("Cameroon", "Tunisia", 1, 0),
        ("Senegal", "Angola", 2, 1),
        ("Ivory Coast", "Nigeria", 3, 1),
    ],
    6: [
        ("Comoros", "Gabon", 2, 1),
        ("DR Congo", "Tanzania", 0, 0),
        ("Benin", "South Africa", 1, 0),
        ("Nigeria", "Cameroon", 0, 0),
        ("Zambia", "Senegal", 0, 1),
        ("Mozambique", "Uganda", 1, 1),
        ("Zimbabwe", "Ivory Coast", 0, 1),
        ("Tunisia", "Sudan", 2, 0),
        ("Burkina Faso", "Mali", 0, 0),
        ("Morocco", "Angola", 4, 0),
        ("Egypt", "Equatorial Guinea", 4, 0),
        ("Botswana", "Algeria", 0, 4),
    ],
    7: [
        ("Angola", "Tunisia", 0, 2),
        ("Sudan", "Nigeria", 0, 0),
        ("Ivory Coast", "Burkina Faso", 1, 1),
        ("Cameroon", "Zimbabwe", 0, 0),
        ("Uganda", "Comoros", 0, 0),
        ("Senegal", "Morocco", 2, 2),
        ("Tanzania", "Algeria", 0, 0),
        ("South Africa", "Egypt", 2, 0),
        ("Gabon", "Benin", 1, 1),
        ("Equatorial Guinea", "DR Congo", 0, 1),
        ("Mali", "Botswana", 1, 0),
        ("Zambia", "Mozambique", 2, 2),
    ],
    8: [
        ("Benin", "Uganda", 1, 1),
        ("Botswana", "Ivory Coast", 0, 1),
        ("Burkina Faso", "Cameroon", 1, 1),
        ("Comoros", "Zambia", 1, 0),
        ("Zimbabwe", "Sudan", 1, 0),
        ("Mozambique", "Senegal", 0, 1),
        ("Nigeria", "Angola", 0, 0),
        ("Egypt", "Gabon", 0, 1),
        ("Algeria", "Equatorial Guinea", 6, 0),
        ("Tanzania", "Mali", 0, 0),
        ("DR Congo", "South Africa", 2, 1),
        ("Tunisia", "Morocco", 1, 0),
    ],
    9: [
        ("Morocco", "Nigeria", 1, 0),
        ("Gabon", "DR Congo", 0, 3),
        ("Ivory Coast", "Tanzania", 1, 1),
        ("Zambia", "Benin", 2, 2),
        ("Equatorial Guinea", "Mali", 0, 0),
        ("Cameroon", "Botswana", 1, 0),
        ("Sudan", "Burkina Faso", 1, 0),
        ("South Africa", "Algeria", 3, 1),
        ("Senegal", "Tunisia", 2, 1),
        ("Angola", "Zimbabwe", 1, 0),
        ("Mozambique", "Comoros", 2, 1),
        ("Uganda", "Egypt", 0, 4),
    ],
    10: [
        ("Zimbabwe", "Morocco", 0, 0),
        ("Botswana", "Sudan", 3, 1),
        ("DR Congo", "Uganda", 0, 1),
        ("Equatorial Guinea", "Ivory Coast", 1, 1),
        ("Nigeria", "Tunisia", 1, 0),
        ("Senegal", "Mali", 1, 0),
        ("South Africa", "Egypt", 0, 0),
        ("Zambia", "Algeria", 5, 0),
        ("Gabon", "Burkina Faso", 1, 1),
        ("Angola", "Tanzania", 1, 0),
        ("Cameroon", "Benin", 1, 3),
        ("Mozambique", "Comoros", 0, 1),
    ],
    11: [
        ("Angola", "Botswana", 1, 2),
        ("Tunisia", "Zimbabwe", 1, 1),
        ("Morocco", "Burkina Faso", 4, 0),
        ("Senegal", "Nigeria", 2, 1),
        ("Comoros", "Benin", 2, 0),
        ("Mozambique", "Egypt", 1, 1),
        ("South Africa", "Ivory Coast", 0, 0),
        ("Sudan", "Tanzania", 1, 2),
        ("Cameroon", "Equatorial Guinea", 5, 1),
        ("Uganda", "Algeria", 0, 2),
        ("Zambia", "DR Congo", 1, 0),
        ("Gabon", "Mali", 0, 2),
    ],
}

def actual_result(sd, se):
    if sd > se: return "1"
    if se > sd: return "2"
    return "X"

def actual_dc(sd, se):
    r = actual_result(sd, se)
    return {"1X": r in ("1","X"), "X2": r in ("X","2"), "12": r in ("1","2")}

with open("D:/Documents/261CAF/historique_predictions.json", "r", encoding="utf-8") as f:
    history = json.load(f)

c5 = [e for e in history if e.get("cycle") == 5]
c5_by_round = {}
for e in c5:
    r = e["round"]
    if r not in c5_by_round or e.get("has_result"):
        c5_by_round[r] = e

print("=" * 80)
print("COMPARISON: User bet261 results vs Our C5 predictions")
print("=" * 80)

total_m = 0
correct_1x2 = 0
correct_dc = 0
score_correct = 0
score_wrong = 0
pairing_issues = []

for rnd in sorted(USER.keys()):
    user_matches = USER[rnd]
    our_entry = c5_by_round.get(rnd)

    if not our_entry:
        print("\n--- R%d: NO PREDICTION (missing from C5) ---" % rnd)
        pairing_issues.append(("R%d" % rnd, "MISSING"))
        continue

    our_preds = our_entry.get("predictions", [])
    our_has_result = our_entry.get("has_result")

    our_by_pair = {}
    for p in our_preds:
        key = (p.get("home_team", ""), p.get("away_team", ""))
        our_by_pair[key] = p

    pairings_ok = True
    r_correct_1x2 = 0
    r_correct_dc = 0
    r_total = 0
    r_score_ok = 0
    r_score_wrong = 0

    print("\n--- R%d (stored acc=%s, src=%s) ---" % (
        rnd, our_entry.get("accuracy_result"),
        [p.get("result_source","?")[0:4] for p in our_preds[:1]]))

    for user_h, user_a, user_sd, user_se in user_matches:
        key = (user_h, user_a)
        op = our_by_pair.get(key)
        if not op:
            pairings_ok = False
            op_rev = our_by_pair.get((user_a, user_h))
            if op_rev:
                print("  %s vs %s: PAIRING REVERSED (actual %d:%d)" % (user_h, user_a, user_sd, user_se))
            else:
                print("  %s vs %s: NOT IN OUR PREDICTIONS (actual %d:%d)" % (user_h, user_a, user_sd, user_se))
            continue

        pc = op.get("res_code", "?")
        pdc = op.get("dc_pred", "?")
        has_r = op.get("has_result")
        our_sd = op.get("actual_score_dom")
        our_se = op.get("actual_score_ext")
        src = op.get("result_source", "none")

        ur = actual_result(user_sd, user_se)
        udc = actual_dc(user_sd, user_se)
        ok_1x2 = (pc == ur)
        ok_dc = udc.get(pdc, False)

        r_total += 1
        total_m += 1
        if ok_1x2:
            r_correct_1x2 += 1
            correct_1x2 += 1
        if ok_dc:
            r_correct_dc += 1
            correct_dc += 1

        score_tag = ""
        if has_r and our_sd is not None:
            if our_sd == user_sd and our_se == user_se:
                r_score_ok += 1
                score_correct += 1
                score_tag = " [score OK %d:%d]" % (our_sd, our_se)
            else:
                r_score_wrong += 1
                score_wrong += 1
                score_tag = " [score WRONG our=%d:%d real=%d:%d src=%s]" % (our_sd, our_se, user_sd, user_se, src)
        else:
            score_tag = " [no result stored]"

        mark = "+" if ok_1x2 else "-"
        dmark = "+" if ok_dc else "-"
        print("  %s %s vs %s: pred=%s dc=%s real=%d:%d 1x2=%s dc=%s%s" % (
            mark, user_h, user_a, pc, pdc, user_sd, user_se,
            "OK" if ok_1x2 else "WRONG", "OK" if ok_dc else "WRONG", score_tag))

    if not pairings_ok:
        pairing_issues.append(("R%d" % rnd, "WRONG PAIRINGS"))

    pct_1x2 = 100 * r_correct_1x2 / r_total if r_total else 0
    pct_dc = 100 * r_correct_dc / r_total if r_total else 0
    print("  >> R%d: 1X2=%d/%d (%.0f%%) DC=%d/%d (%.0f%%) scores_ok=%d scores_wrong=%d pairings=%s" % (
        rnd, r_correct_1x2, r_total, pct_1x2, r_correct_dc, r_total, pct_dc,
        r_score_ok, r_score_wrong, "OK" if pairings_ok else "WRONG"))

print("\n" + "=" * 80)
print("GRAND TOTAL")
print("=" * 80)
print("Matches compared: %d (out of %d user results)" % (total_m, sum(len(v) for v in USER.values())))
if total_m > 0:
    print("1X2 accuracy: %d/%d = %.1f%%" % (correct_1x2, total_m, 100 * correct_1x2 / total_m))
    print("DC  accuracy: %d/%d = %.1f%%" % (correct_dc, total_m, 100 * correct_dc / total_m))
print("Score accuracy: %d/%d = %.1f%% (of stored scores)" % (score_correct, score_correct + score_wrong,
    100 * score_correct / (score_correct + score_wrong) if score_correct + score_wrong else 0))
print("Score wrong: %d (playout/CSV data from wrong cycles)" % score_wrong)
print("\nPairing issues: %s" % pairing_issues)
print("Missing rounds: R4 (collector skipped)")
