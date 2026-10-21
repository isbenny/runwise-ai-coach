#!/usr/bin/env python3
"""Offline adapter for unchanged Core rules. No auth, network or persistent DB."""
import argparse
from contextlib import contextmanager
from datetime import date,datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'_core'))
try:
    from jsonschema import Draft202012Validator,FormatChecker
    from garmin_ai_coach.core_schema import CoreError,PROFILE,FEEDBACK,validate,RULE_VERSION
    from garmin_ai_coach.core_analysis import ActivityAnalysis
    from garmin_ai_coach.core_plans import training_basis,initial_plan,adjusted_plan,validate_plan
    from garmin_ai_coach.repository import _insert_activity,_source,upsert_laps
    from garmin_ai_coach.quality import refresh_metric_quality
except ImportError:
    print(json.dumps({'status':'needs_capability','missing':'Python + jsonschema==4.26.0 in host-isolated environment; no dependency auto-installed'}));sys.exit(2)


def obj(properties,required):return dict(type='object',properties=properties,required=required,additionalProperties=False)
NUMBER={'type':['number','null']}
METRICS='distance_m timer_s moving_s elapsed_s avg_hr_bpm max_hr_bpm avg_power_w'
LAP=obj(dict(lap_no={'type':'integer','minimum':1},lap_type={'type':'string','maxLength':60},**{k:NUMBER for k in METRICS.split()}),['lap_no','lap_type','distance_m','timer_s'])
ACTIVITY=obj(dict(source_id={'type':'string','minLength':1,'maxLength':128},kind={'enum':['running','track_running','cycling','other']},started_at={'type':'string','format':'date-time'},
    timezone_assumption={'type':['string','null'],'maxLength':100},**{k:NUMBER for k in METRICS.split()},laps={'type':'array','items':LAP,'maxItems':500},
    laps_complete={'type':'boolean'},lap_source_tool={'type':['string','null'],'maxLength':100}),['source_id','kind','started_at','distance_m','timer_s','laps','laps_complete'])
INPUT=obj(dict(schema_version={'const':'runwise-mcp-input/1'},provider={'enum':['garmin','coros']},region={'enum':['garmin.cn','coros.cn']},as_of={'type':'string','format':'date'},
    source_tool={'type':'string','minLength':1,'maxLength':100},coverage=obj(dict(start={'type':'string','format':'date'},end={'type':'string','format':'date'},complete={'type':'boolean'}),['start','end','complete']),
    activities={'type':'array','items':ACTIVITY,'maxItems':2000}),['schema_version','provider','region','as_of','source_tool','coverage','activities'])
WEEKDAYS=['周一','周二','周三','周四','周五','周六','周日']


def read(path):
    if path.is_symlink() or path.stat().st_size>10_000_000:raise CoreError('LOCAL_INPUT_INVALID')
    return json.loads(path.read_text())


def calendar(as_of,plan=None):
    monday=as_of-timedelta(days=as_of.weekday());sessions=(plan or {}).get('sessions',[])
    rows=[dict(date=x['date'],weekday_zh=WEEKDAYS[date.fromisoformat(x['date']).weekday()],session=x) for x in sessions]
    return dict(timezone='Asia/Shanghai',as_of=as_of.isoformat(),weekday_zh=WEEKDAYS[as_of.weekday()],natural_week_start=monday.isoformat(),natural_week_end=(monday+timedelta(days=6)).isoformat(),
                sessions=rows,next_scheduled_session=next((x for x in rows if x['date']>as_of.isoformat()),None))


class MemorySnapshot:
    def __init__(self,value):
        errors=list(Draft202012Validator(INPUT,format_checker=FormatChecker()).iter_errors(value))
        if errors:raise CoreError('MCP_INPUT_CONTRACT_INVALID')
        if value['region']!=value['provider']+'.cn':raise CoreError('PROVIDER_REGION_MISMATCH')
        self.value=value;self.as_of=date.fromisoformat(value['as_of'])
        if self.as_of>datetime.now(ZoneInfo('Asia/Shanghai')).date():raise CoreError('AS_OF_FROM_FUTURE')
        if not value['coverage']['start']<=value['coverage']['end']<=value['as_of']:raise CoreError('COVERAGE_INVALID')
        self.conn=sqlite3.connect(':memory:');self.conn.row_factory=sqlite3.Row;self.conn.execute('PRAGMA foreign_keys=ON')
        for p in sorted((HERE/'_core/garmin_ai_coach/migrations').glob('*.sql')):self.conn.executescript(p.read_text())
        self.ids={};seen={}
        for item in sorted(value['activities'],key=lambda x:(x['started_at'],x['source_id'])):
            key=item['source_id'];encoded=json.dumps(item,sort_keys=True,allow_nan=False)
            if key in seen:
                if seen[key]!=encoded:raise CoreError('DUPLICATE_SOURCE_ID_CONFLICT')
                continue
            seen[key]=encoded;at=datetime.fromisoformat(item['started_at'].replace('Z','+00:00'))
            if at.tzinfo is None:raise CoreError('EXPLICIT_TIMEZONE_REQUIRED')
            local=at.astimezone(ZoneInfo('Asia/Shanghai'))
            if not value['coverage']['start']<=local.date().isoformat()<=value['coverage']['end']:raise CoreError('ACTIVITY_OUTSIDE_COVERAGE')
            activity=dict(provider=value['provider'],region=value['region'],provider_activity_id=key,kind=item['kind'],type_key=item['kind'],started_at_raw=item['started_at'],
                started_at_local=local.isoformat(),started_at_utc=at.astimezone(timezone.utc).isoformat(),local_date=local.date().isoformat(),timezone_basis=item.get('timezone_assumption') or 'explicit_source_offset',
                **{k:item.get(k) for k in METRICS.split()})
            aid=_insert_activity(self.conn,activity);self.ids[key]=aid
            _source(self.conn,aid,value['provider'],value['region'],key,label=value['source_tool'])
            if item['laps']:
                if not item.get('lap_source_tool') or len({x['lap_no'] for x in item['laps']})!=len(item['laps']):raise CoreError('LAP_SOURCE_OR_ID_INVALID')
                issues=[('negative_lap_value','Negative source lap value retained for review')] if any(x.get(k) is not None and x[k]<0 for x in item['laps'] for k in METRICS.split()) else []
                upsert_laps(self.conn,aid,item['laps'],issues)
                self.conn.execute('UPDATE activity_lap SET source_kind=? WHERE activity_id=?',(value['provider']+'_laps',aid))
                if not item['laps_complete']:self.conn.execute("UPDATE activity SET lap_status='partial' WHERE id=?",(aid,))
            elif item['laps_complete']:raise CoreError('EMPTY_LAPS_CANNOT_BE_VERIFIED')
        refresh_metric_quality(self.conn);self.conn.commit()

    @contextmanager
    def database(self,**_):yield self.conn

    def basis(self):return training_basis(self.conn,self.as_of)

    def full_coverage(self):
        c=self.value['coverage'];return c['complete'] and c['start']<=(self.as_of-timedelta(days=41)).isoformat() and c['end']==self.as_of.isoformat()


def run(args):
    if args.command=='contracts':return dict(input=INPUT,profile=PROFILE,feedback=FEEDBACK,rule_version=RULE_VERSION)
    value=read(args.input);snapshot=MemorySnapshot(value)
    try:
        common=dict(rule_version=RULE_VERSION,source=dict(kind='mcp_snapshot_in_memory',provider=value['provider'],region=value['region'],tool=value['source_tool'],coverage=value['coverage']),
                    persisted=False,limitations=['只读输入快照；无联网、数据库文件或正式计划保存。','覆盖不全时统计只是已取得的数据，不代表全部训练。'])
        if args.command=='report':
            activity='latest' if args.activity=='latest' else snapshot.ids.get(args.activity)
            if activity is None:raise CoreError('SOURCE_ACTIVITY_NOT_FOUND')
            report=ActivityAnalysis(snapshot).analyze(activity,as_of=snapshot.as_of)
            report['source'].update(common['source']);report['limitations']+=common['limitations']
            return dict(**common,report=report,calendar=calendar(snapshot.as_of))
        if not snapshot.full_coverage():return dict(**common,status='needs_information',missing=['verified_complete_42_day_coverage'],calendar=calendar(snapshot.as_of))
        profile=read(args.profile);validate(profile,PROFILE);basis=snapshot.basis()
        if args.command=='plan':
            plan=initial_plan(profile,basis,date.fromisoformat(args.start),snapshot.as_of,program='marathon')
            return dict(**common,status=plan.get('status','draft'),plan=plan,calendar=calendar(snapshot.as_of,plan))
        original=read(args.plan);original=original.get('data',original)
        feedback=read(args.feedback);validate(feedback,FEEDBACK)
        observed=datetime.fromisoformat(feedback['observed_at'].replace('Z','+00:00'))
        if observed.tzinfo is None or observed.astimezone(ZoneInfo('Asia/Shanghai')).date()>snapshot.as_of:raise CoreError('FEEDBACK_TIME_INVALID')
        if (snapshot.as_of-observed.astimezone(ZoneInfo('Asia/Shanghai')).date()).days>7:raise CoreError('FEEDBACK_TOO_OLD')
        if args.activity=='latest' or args.activity not in snapshot.ids:raise CoreError('EXPLICIT_FEEDBACK_ACTIVITY_REQUIRED')
        activity=snapshot.conn.execute('SELECT started_at_utc FROM activity WHERE id=?',(snapshot.ids[args.activity],)).fetchone()
        if observed<datetime.fromisoformat(activity[0]):raise CoreError('FEEDBACK_BEFORE_ACTIVITY')
        validate_plan(original,profile)
        proposal=adjusted_plan(original,feedback,as_of=snapshot.as_of,days=args.days,recent_long_exposures=basis['recent_long_exposures'],training_basis=basis)
        validate_plan(proposal['suggested_plan'],profile)
        return dict(**common,status='draft',original_plan=original,proposal=proposal,calendar=calendar(snapshot.as_of,proposal['suggested_plan']),
                    evidence_activity=ActivityAnalysis(snapshot).analyze(snapshot.ids[args.activity],as_of=snapshot.as_of),
                    execution_comparison='unverified: snapshot alone does not prove a pre-existing formal target; no objective overshoot classification')
    finally:snapshot.conn.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['contracts','report','plan','adjust']);p.add_argument('--input',type=Path);p.add_argument('--profile',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--feedback',type=Path);p.add_argument('--activity',default='latest');p.add_argument('--start');p.add_argument('--days',type=int,default=7);p.add_argument('--output',type=Path);a=p.parse_args();os.umask(0o077)
    try:
        result=run(a);text=json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)
        if a.output:
            # Never silently overwrite a saved plan or profile.
            with a.output.open('x') as f:f.write(text+'\n')
        else:print(text)
    except (CoreError,ValueError,KeyError,TypeError,AttributeError,FileExistsError):print(json.dumps({'status':'error','code':'INVALID_OR_INCOMPLETE_INPUT_CHECK_CONTRACT_NO_WRITE'}));sys.exit(2)
