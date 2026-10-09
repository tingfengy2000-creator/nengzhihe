"""Small independent accounting/source checks, not accuracy tests."""
from __future__ import annotations
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'operation_planning/results/round23_case_admission'
BASE='e7f0cf1d0eed5464835897c1d51db84040cb16a0'


def read(name):
    with (DATA/name).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def main():
    checks=[]
    def check(name,condition,actual):
        checks.append({'check':name,'status':'pass' if condition else 'fail','actual':actual})
        if not condition:raise AssertionError(name)
    cu=json.loads((DATA/'cu_summary.json').read_text(encoding='utf-8'))
    month=read('cu_floor2_ac_observed_months.csv')
    check('minute_axis_and_column_count',cu['rows']==525600 and cu['measurement_columns']==36 and cu['duplicates']==0,
          {'rows':cu['rows'],'columns':cu['measurement_columns'],'duplicates':cu['duplicates']})
    check('monthly_expected_minutes',sum(int(r['expected_minutes']) for r in month)==525600,525600)
    observed=sum(float(r['observed_all_16_ac_energy_kwh']) for r in month)
    check('monthly_observed_integral_reconciles',abs(observed-cu['observed_joint_ac_energy_kwh'])<1e-8,observed)
    check('unknown_annual_energy_is_null',cu['full_year_ac_energy_kwh'] is None and cu['complete_ac_channels']==0,
          {'annual':cu['full_year_ac_energy_kwh'],'complete_channels':cu['complete_ac_channels']})
    check('missing_months_not_zero',all((r['complete_month_energy_kwh']=='') if int(r['jointly_valid_ac_minutes'])<int(r['expected_minutes']) else r['complete_month_energy_kwh']!='' for r in month),
          {'incomplete_months':sum(r['complete_month_energy_kwh']=='' for r in month)})
    week=read('cu_measured_week_hourly.csv')
    check('week_preserves_missing_hours',len(week)==168 and all(r['complete_hour_energy_kwh']=='' for r in week if int(r['valid_minutes'])<60),
          {'hour_intervals':len(week),'incomplete_hours':sum(r['complete_hour_energy_kwh']=='' for r in week)})
    madrid=json.loads((DATA/'madrid_summary.json').read_text(encoding='utf-8'))
    rows=read('madrid_selected_12_months.csv')
    total=sum(Decimal(r['consumption_raw'].replace(',','.')) for r in rows)
    check('12_unique_months',len(rows)==12 and {int(r['month']) for r in rows}==set(range(1,13)),len(rows))
    check('decimal_source_sum',abs(total-Decimal(str(madrid['annual_meter_energy_kwh'])))<Decimal('0.000001'),str(total))
    check('no_fabricated_bill_or_AC_split',all(r['billing_amount_eur']=='' and r['ac_submeter_kwh']=='' for r in rows),
          {'invoice_available':madrid['invoice_available'],'ac_submeter_available':madrid['ac_submeter_available']})
    raw=ROOT/'working/round23/sources/2019Floor2.csv'
    metadata=json.loads((ROOT/'working/round23/sources/cu_metadata.json').read_text(encoding='utf-8'))
    declared=next(f['computed_md5'] for f in metadata['files'] if f['name']=='2019Floor2.csv')
    actual=hashlib.md5(raw.read_bytes()).hexdigest()
    check('download_matches_publisher_md5',actual==declared,actual)
    manifest=json.loads((DATA/'analysis_run_manifest.json').read_text(encoding='utf-8'))
    frozen=[]
    for name,expected in manifest['frozen_backend_hashes'].items():
        historical=subprocess.check_output(['git','show',f'{BASE}:{name}'],cwd=ROOT)
        # Existing checkout is CRLF-normalized in some files. Compare via git
        # object bytes, rather than treating line-ending changes as formulas.
        current=subprocess.check_output(['git','show',f'HEAD:{name}'],cwd=ROOT)
        assert current==historical
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected
        frozen.append(name)
    check('frozen_backend_unchanged',len(frozen)==5,frozen)
    result={'scope':'11 source/accounting checks; not model-accuracy or field-performance evidence',
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':checks,
            'pass':sum(x['status']=='pass' for x in checks),'fail':sum(x['status']=='fail' for x in checks)}
    (DATA/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pass':result['pass'],'fail':result['fail'],'scope':result['scope']},ensure_ascii=False))


if __name__=='__main__':main()
