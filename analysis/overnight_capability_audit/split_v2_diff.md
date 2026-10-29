# inner_split_seed1337 v1 -> v2 diff + verification
v1: population dev-minus-quarantine = 1233 (seed 1337, 863/185/185). v2: full dev = 1237 (seed 1337, 866/185/186). v1 file was only read, never overwritten. All counts below are recomputed from data + manifests.
## 1. v2 structural verification (independent)
- counts: {'inner_train': 866, 'inner_test': 186, 'inner_val': 185}; disjoint: True; held-out ids: 0; near-dup group in train: ['train_0061', 'train_0066', 'train_0168']; train_eligible False: only train_1696.
- inner_train: n=866, kind={'ask_after': 0.1016, 'ask_only': 0.0393, 'empty': 0.0716, 'normal': 0.7875}, history=0.6582, rbw={'no_write': 0.2367, 'write_after_read': 0.5035, 'write_without_prior_read': 0.2598} -> within +/-2pp of population: True
- inner_val: n=185, kind={'ask_after': 0.1081, 'ask_only': 0.0378, 'empty': 0.0703, 'normal': 0.7838}, history=0.6541, rbw={'no_write': 0.2486, 'write_after_read': 0.5027, 'write_without_prior_read': 0.2486} -> within +/-2pp of population: True
- inner_test: n=186, kind={'ask_after': 0.0968, 'ask_only': 0.0376, 'empty': 0.0753, 'normal': 0.7903}, history=0.6613, rbw={'no_write': 0.2312, 'write_after_read': 0.5054, 'write_without_prior_read': 0.2634} -> within +/-2pp of population: True

## 2. v1 -> v2 diff
- common ids: 1233; moved part: 124; added (quarantine returned): ['train_1005', 'train_1033', 'train_1319', 'train_1696'] -> [('train_1005', 'inner_test'), ('train_1033', 'inner_train'), ('train_1319', 'inner_train'), ('train_1696', 'inner_train')]; removed: [].
- counts v1 -> v2 per part: {'inner_train': 863, 'inner_test': 185, 'inner_val': 185} -> {'inner_train': 866, 'inner_test': 186, 'inner_val': 185}.
- kind delta inner_train: {'normal': 3, 'ask_after': 0, 'empty': 0, 'ask_only': 0}
- kind delta inner_val: {'normal': -2, 'ask_after': 3, 'empty': -1, 'ask_only': 0}
- kind delta inner_test: {'normal': 3, 'ask_after': -3, 'empty': 1, 'ask_only': 0}
- moved ids (124): train_0007, train_0089, train_0180, train_0192, train_0217, train_0225, train_0291, train_0315, train_0441, train_0455, train_0493, train_0651, train_0652, train_0755, train_0770, train_0820, train_0950, train_1004, train_1014, train_1016, train_1017, train_1059, train_1070, train_1072, train_1074, train_1080, train_1084, train_1095, train_1110, train_1118, train_1121, train_1138, train_1148, train_1153, train_1158, train_1159, train_1165, train_1175, train_1178, train_1179, train_1186, train_1196, train_1199, train_1201, train_1203, train_1204, train_1205, train_1209, train_1213, train_1221, train_1229, train_1236, train_1238, train_1256, train_1262, train_1271, train_1277, train_1279, train_1289, train_1290, train_1291, train_1294, train_1305, train_1308, train_1310, train_1314, train_1317, train_1318, train_1324, train_1325, train_1326, train_1327, train_1336, train_1338, train_1340, train_1341, train_1344, train_1354, train_1361, train_1362, train_1369, train_1375, train_1379, train_1384, train_1385, train_1411, train_1413, train_1414, train_1417, train_1422, train_1423, train_1426, train_1435, train_1445, train_1454, train_1463, train_1471, train_1500, train_1504, train_1509, train_1523, train_1542, train_1544, train_1560, train_1564, train_1567, train_1568, train_1576, train_1590, train_1594, train_1597, train_1609, train_1631, train_1649, train_1663, train_1667, train_1681, train_1682, train_1686, train_1697, train_1698, train_1702, train_1709, train_1717
- Why so many moves are expected: v2 re-runs the identical stratified procedure (seed 1337) on a different population (1237 vs 1233); cell membership changes shift in-cell shuffle order. v1 was a proposal never used for training, so re-running costs nothing; hand-placing only 4 ids would have introduced placement bias.

## 3. Audio checks (dev paths only)
- dev audio paths inventoried: 4033 (current: 1237, history: 2796); files missing on disk: 0 [].
- sha256 computed: 4033; distinct hashes: 4033; content collisions (same hash, different paths): 0.
- collisions crossing v2 parts: 0 [].
- CONTENT-DISJOINT (dev audio, v2 parts): no two different dev audio paths share content, so no content overlap exists across parts. (This is a statement about referenced dev audio files only; it says nothing about held-out audio, which was never opened.)

## 4. Tool-sequence overlap (exact gold call-name sequences)
- distinct gold tool sequences in dev: 582.
- inner_val: 106/185 samples (57.3%) have an exact gold tool sequence that also occurs in train. This is EXPECTED (582 distinct sequences over 1237 samples) and is reported, not hidden; it is why a random split measures new requests with familiar behaviours, not unseen behaviour.
- inner_test: 115/186 samples (61.8%) have an exact gold tool sequence that also occurs in train. This is EXPECTED (582 distinct sequences over 1237 samples) and is reported, not hidden; it is why a random split measures new requests with familiar behaviours, not unseen behaviour.

## 5. Template groups (normalized request text)
- normalized (fold + digit-mask): 1235 groups; multi-member groups: 1; groups straddling v2 parts: 0.
- entity-masked secondary (queries -> #NAME): 1235 groups; multi-member groups: 1; groups straddling v2 parts: 0.
- No 'template-disjoint' claim is made: shared normalized text is a shared TEXT TEMPLATE only. Behaviour-template (tool-sequence) overlap is reported separately in section 4.
