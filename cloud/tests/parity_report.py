"""Print an old-vs-new comparison for the demo proposal: python3 cloud/tests/parity_report.py"""
import numpy as np
from test_effort import load_demo

d, members, goals, r = load_demo()
kinds = ('total', 'unfunded', 'funded')
print('PERSON FTE PER YEAR  (Sheet -> new engine)')
print(f"{'person':8}{'year':>6}" + ''.join(f'{k:>20}' for k in kinds))
for p, new_py, new_tot in zip(d['team'], r['person_year'], r['person_total']):
    old_py = np.array(p['sheet_fte_per_year'][:d['n_years']])
    for y in range(d['n_years']):
        print(f"{p['id']:8}{y + 1:>6}" + ''.join(f'{o:>9.2f} -> {n:<5.2f}{"  " if abs(o - n) < 1e-9 else " *"}' for o, n in zip(old_py[y], new_py[y])))
    print(f"{p['id']:8}{'all':>6}" + ''.join(f'{o:>9.2f} -> {n:<5.2f}{"  " if abs(o - n) < 1e-9 else " *"}' for o, n in zip(p['sheet_fte_total'], new_tot)))
print('\nTASK FTE  (Sheet -> new engine)')
old_tasks = [(t['sheet_id'], t['title'], t['sheet_fte']) for g in d['goals'] for t in g['tasks']]
for (sid, title, old), lab in zip(old_tasks, r['leaf_labels']):
    new = r['items'][lab]['fte']
    print(f'{sid:6}{lab:6}{title[:38]:40}' + ''.join(f'{o:>7.3f} -> {n:<6.3f}{"  " if abs(o - n) < 1e-9 else " *"}' for o, n in zip(old, new)))
print('\nPROJECT TOTAL (new):', ' / '.join(f'{k} {v:.2f}' for k, v in zip(kinds, r['project_total'])))
print('CHECKS:', [f'{c.item}: {c.message}' for c in r['checks']] or 'none')
print('\n* marks a difference')
